"""Recover omitted interface coordinates from exported spring geometry only."""
from functools import lru_cache
import numpy as np


@lru_cache(maxsize=32)
def fibre_weights(nrow, ncol):
    """C# Getdi/EccSpring use bilinear weights at each fibre's centre."""
    if nrow < 2 or ncol < 2:
        raise ValueError("Insufficient spring grid to recover interface geometry.")
    u, v = np.meshgrid(-1 + (2*np.arange(ncol)+1)/ncol,
                       -1 + (2*np.arange(nrow)+1)/nrow)
    return np.column_stack([((1+su*u)*(1+sv*v)/4).ravel()
                            for su, sv in [(-1,-1),(1,-1),(1,1),(-1,1)]])


def interface_geometry(geometry, state):
    if geometry.get("reference_origin") is not None and geometry.get("vint2d") is not None:
        return geometry
    weights = fibre_weights(int(geometry["nrow"]), int(geometry["ncol"]))
    springs = state["trasv_1"]
    centres = np.asarray([[s["di"], s["ecc"]] for s in springs], dtype=float)
    if centres.shape != (len(weights), 2) or not np.isfinite(centres).all():
        raise ValueError("Invalid saved fibre coordinates.")
    local, _, _, _ = np.linalg.lstsq(weights, centres, rcond=None)
    if not np.allclose(weights @ local, centres, rtol=0, atol=1e-7):
        raise ValueError("Saved fibres do not define a consistent bilinear interface.")
    axes = np.column_stack([geometry["reference_e1"], geometry["reference_e3"]])
    corners = np.asarray(geometry["vint3d"], dtype=float)
    translations = corners - local @ axes.T
    origin = translations.mean(axis=0)
    # The export's world corners and reference axes have float32 precision.
    if corners.shape != (4, 3) or not np.isfinite(translations).all() or not np.allclose(translations, origin, rtol=0, atol=5e-4):
        raise ValueError("Global interface corners disagree with saved fibre coordinates.")
    return {**geometry, "vint2d": local.astype(np.float32).tolist(),
            "reference_origin": origin.astype(np.float32).tolist(),
            "geometrySource": "Recovered from saved fibre di/ecc and world corners"}
