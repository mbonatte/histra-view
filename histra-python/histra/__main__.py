"""
HiStrA-Python: structural analysis solver CLI.

Usage:
    python -m histra model.hrx [--output results.json]
"""
from __future__ import annotations
import sys
import json
import time
import numpy as np

from histra.io.hr_loader import load_model
from histra.solver.assembler import assemble_global_k


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    hrx_path = sys.argv[1]
    output_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]

    print(f"Loading {hrx_path}...")
    t0 = time.time()
    model = load_model(hrx_path)
    t1 = time.time()
    print(f"  Loaded in {t1-t0:.1f}s")
    print(f"  GDL={model.gdl}, Quads={len(model.collections.quads)}, "
          f"Interfaces={len(model.collections.interfaces)}, "
          f"Nodes={len(model.collections.nodes)}, "
          f"NodeCs={len(model.collections.node_c)}, "
          f"Restraints={len(model.collections.restraints)}")

    print("\nAssembling K (alfa=0)...")
    t0 = time.time()
    K = assemble_global_k(model, alfa=0.0)
    t1 = time.time()
    print(f"  Assembled in {t1-t0:.1f}s")
    print(f"  K shape={K.shape}, nnz={K.nnz}, density={K.nnz/(K.shape[0]**2)*100:.3f}%")
    print(f"  K diagonal range: [{K.diagonal().min():.4e}, {K.diagonal().max():.4e}]")

    # For verification: use displacements from the .hrx post-solve state
    from histra.solver.assembler import extract_displacements
    u = extract_displacements(model)
    non_zero = np.count_nonzero(np.abs(u) > 1e-20)
    print(f"\n  Solution: {non_zero}/{model.gdl} non-zero displacements")

    # Summary statistics
    abs_u = np.abs(u)
    print(f"  |u| range: [{abs_u.min():.6e}, {abs_u.max():.6e}]")
    print(f"  |u| mean: {abs_u.mean():.6e}")

    if output_path:
        results = {
            "gdl": model.gdl,
            "n_quads": len(model.collections.quads),
            "n_interfaces": len(model.collections.interfaces),
            "n_nodes": len(model.collections.nodes),
            "n_nodecs": len(model.collections.node_c),
            "n_restraints": len(model.collections.restraints),
            "K_nnz": K.nnz,
            "u_min": float(abs_u.min()),
            "u_max": float(abs_u.max()),
            "u_mean": float(abs_u.mean()),
            "displacements": u.tolist(),
        }
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
