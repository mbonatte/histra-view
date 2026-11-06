"""Exact, portable fingerprints of available native spring-state columns."""
import hashlib

import numpy as np

from histra.solver.restart import _spring_targets, capture_committed_spring_state
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic

IDENTITY = ("ParentType", "ParentKey", "SpringPurpose", "IdLocal")
FIELDS = (
    "U", "F", "Phase", "Fy1", "Fy2", "Up1", "Up2", "N", "SpringType", "K_tang",
    "Uy1", "Uy2", "Umax1", "Umax2", "Uu1", "Uu2", "LoadIndicator", "ContactArea", "F0",
    "CmomMin", "CmomMax", "CrotLimNu", "CrotLimPu", "CrotYn", "CrotYp",
    "CPhaseUnload_t", "CPhaseUnload_c", "TangentReload_c", "TangentReload_t",
    "CplasticTensionIndicator", "CplasticCompressionIndicator",
)


def fingerprint(keys, values):
    identities = np.asarray(keys, dtype="<i8")
    numbers = np.asarray(values, dtype="<f8").copy()
    if not np.all(np.isfinite(numbers)):
        raise ValueError("Nonfinite state cannot receive an exact parity fingerprint")
    numbers[numbers == 0.0] = 0.0  # SQLite does not retain negative-zero storage.
    return {"rows": len(keys), "identities": hashlib.sha256(identities.tobytes()).hexdigest(),
            "values": hashlib.sha256(numbers.tobytes()).hexdigest()}


def python_spring_rows(model):
    from histra.solver.model_manager import ModelManager
    runtime = ModelManager.hysteretic_batch_for(model)
    if runtime is not None:
        runtime.sync_all_to_objects()
    rows = []
    for key, spring in sorted(_spring_targets(model)):
        values = dict.fromkeys(FIELDS, 0.0)
        values.update(capture_committed_spring_state(spring))
        values.update(U=float(spring.u), F=float(spring.f), K_tang=float(spring.k_tang),
                      ContactArea=float(getattr(spring, "_ccontact_area", spring.area)))
        values["SpringType"] = (12 if isinstance(spring, SpringCoulomb03) else
                                8 if isinstance(spring, SpringHysteretic) else
                                1 if isinstance(spring, SpringElastic) else -1)
        rows.append((key, values))
    return rows
