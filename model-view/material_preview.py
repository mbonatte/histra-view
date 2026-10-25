"""Isolated material coupon previews using the existing Python spring laws.

The unit-area, unit-length coupon follows C# MaterialBase.GetStress and
MasonryMaterial.GetShearStress/GetSlidingStress. No model is loaded or solved.
Run under the viewer's Python environment, with JSON on stdin/stdout.
"""
from dataclasses import replace
from pathlib import Path
import json
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "histra-python"))


def _make_spring(attributes, mechanism, direction):
    from histra.model.masonry_material import MasonryMaterial
    from histra.preprocessing.constitutive_laws import (
        CoulombLaw, flex_law, shear_law, sliding_law,
    )
    from histra.preprocessing.spring_factory import (
        _configure_hysteretic, _configure_coulomb, _set_coulomb_ultimate,
    )
    from histra.springs.elastic import SpringElastic

    material = MasonryMaterial(key=int(attributes.get("Key", 0)), properties=attributes)
    if mechanism == "rocking":
        law = flex_law(material, vertical=direction == "2")
        # C# SetFiberSection converts energy per metre to the 1 cm coupon.
        law = replace(law, G_t=law.G_t / 100, G_c=law.G_c / 100,
                      is_elastic=law.tensile_curve == "Elastic")
        spring = _configure_hysteretic(law.E, 1.0, 1.0, law)
        strain = max(law.fy_t, law.fy_c) / law.E
        return spring, max(strain * 1.5, 1e-6)
    k = float(material.value("Gd", 0.0))
    if not math.isfinite(k) or k <= 0:
        raise ValueError("The saved shear modulus Gd must be positive.")
    law = shear_law(material) if mechanism == "shear" else sliding_law(
        material, out_of_plane=False, direction={"1": "hor", "2": "vert", "3": "dir3"}[direction])
    if not isinstance(law, CoulombLaw):
        # Native zero-friction shear dispatch uses a transverse hysteretic law.
        spring = _configure_hysteretic(k, 1.0, 1.0, law)
        return spring, max(abs(law.fy_t / k) * 3, 1e-6)
    if law.is_elastic or law.sub_law == "Linear":
        return SpringElastic(k=k, area=1.0, length=1.0), max(law.cohesion / k * 3, 0.001)
    if mechanism == "sliding":
        # Native preview uses Gd for the coupon, rather than interface geometry.
        law = replace(law, G=law.G / 100)
        spring = _configure_coulomb(k=k, area=1.0, length=1.0, law=law,
                                    ur=100000.0, hysteretic_type="Initial")
        _set_coulomb_ultimate(spring, law, law)
    else:
        ultimate = law.ductility
        if law.fracture_energy:
            if law.cohesion <= 0:
                raise ValueError("Shear fracture-energy preview requires positive cohesion.")
            ultimate = law.cohesion / k + law.G / 100 / law.cohesion
        spring = _configure_coulomb(k=k, area=1.0, length=1.0, law=law,
                                    ur=ultimate, hysteretic_type="Takeda",
                                    plastic_strain=ultimate if law.fracture_energy else law.plastic_strain,
                                    use_second_branch=law.plastic_stiffness_ratio2 < 0)
    return spring, max(law.cohesion / k * 3, 1e-6)


def strain_history(amplitude, cycles, points=80, cyclic=True):
    history = [0.0]
    for cycle in range(1, cycles + 1):
        peak = amplitude * cycle / cycles
        targets = [peak, -peak, 0.0] if cyclic else [peak]
        for target in targets:
            start = history[-1]
            history.extend(start + (target - start) * i / points for i in range(1, points + 1))
    return history


def preview(request):
    attributes = request.get("attributes", {})
    if not isinstance(attributes, dict) or len(attributes) > 300:
        raise ValueError("Invalid material attributes.")
    attributes = {str(k): str(v) for k, v in attributes.items()}
    if attributes.get("PurposeType") != "MasonryMaterial" and not attributes.get("TypeOf", "").endswith(".MasonryMaterial"):
        raise ValueError("Only masonry material previews are supported.")
    for value in attributes.values():
        if len(value) > 2000:
            raise ValueError("Material attribute is too long.")
        try:
            numeric = float(value)
        except ValueError:
            continue
        if not math.isfinite(numeric):
            raise ValueError("Material parameters must be finite.")
    mechanism = request.get("mechanism", "rocking")
    direction = str(request.get("direction", "1"))
    if mechanism not in {"rocking", "shear", "sliding"} or direction not in {"1", "2", "3"}:
        raise ValueError("Invalid mechanism or local direction.")
    cycles = int(request.get("cycles", 3))
    if not 1 <= cycles <= 8:
        raise ValueError("Choose between 1 and 8 cycles.")
    spring, suggested = _make_spring(attributes, mechanism, direction)
    amplitude = suggested if request.get("amplitude") in (None, "") else float(request["amplitude"])
    if not math.isfinite(amplitude) or not 1e-10 <= amplitude <= 1:
        raise ValueError("Peak strain must be between 1e-10 and 1.")
    history_type = request.get("history", "cyclic")
    if history_type not in {"cyclic", "monotonic"}:
        raise ValueError("Choose a cyclic or monotonic strain history.")
    history = strain_history(amplitude, cycles, cyclic=history_type == "cyclic")
    result = []
    for strain in history:
        spring.set_trial_strain(strain)
        force = float(spring.get_force())
        spring.commit()
        if not math.isfinite(force):
            raise ValueError("The material law produced a nonfinite stress for this history.")
        result.append([strain, force])
    return {"points": result, "amplitude": amplitude, "cycles": cycles,
            "stressUnit": "kN/cm²", "strainUnit": "dimensionless",
            "mechanism": mechanism, "direction": direction,
            "description": "Virgin material coupon: area 1 cm², gauge length 1 cm; zero applied normal stress. Python spring laws; prescribed strain history, not structural analysis results."}


if __name__ == "__main__":
    try:
        print(json.dumps(preview(json.load(sys.stdin)), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
