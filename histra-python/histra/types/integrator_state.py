from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntegratorState:
    """State data carried through a step integration (port of ``IntegratorState``).

    Attributes:
        step: Current step number.
        lambda_: Current load-factor value.
        dlambda: Load-factor increment for the current step.
        u: Displacement increment vector (n DOFs).
        delta_lambda: Arc-length load-factor increment.
    """
    step: int = 0
    lambda_: float = 0.0
    dlambda: float = 0.0
    u: Any = None  # np.ndarray or list; set externally
    delta_lambda: float = 0.0
