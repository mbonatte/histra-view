"""Manual nonlinear-solver runner; not an automated pytest module."""
from __future__ import annotations

import argparse
from pathlib import Path

from histra.io.hr_loader import load_model
from histra.solver.solve import solve_static_nonlinear


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "model", nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "model-output" / "model.hrx"),
    )
    parser.add_argument("--analysis", type=int, default=1)
    args = parser.parse_args()

    model = load_model(args.model)
    analysis = model.collections.analyses[args.analysis]
    code, steps = solve_static_nonlinear(model, analysis, on_log=print)
    print(f"exit_code={code}, committed_steps={sum(s['status'] == 'OK' for s in steps)}")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
