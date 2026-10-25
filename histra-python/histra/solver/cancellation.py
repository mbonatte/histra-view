"""Cooperative cancellation and process-local solver serialization."""
from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Callable, Iterator


CancelCheck = Callable[[], bool]
CANCELLED_EXIT_CODE = -5


class SolverCancelled(RuntimeError):
    """Raised at a safe solver checkpoint after cancellation is requested."""


def raise_if_cancelled(should_cancel: CancelCheck | None) -> None:
    """Raise :class:`SolverCancelled` when the supplied callback requests it."""
    if should_cancel is not None and bool(should_cancel()):
        raise SolverCancelled("Solver execution was cancelled.")


# ModelManager currently publishes active vectors through class attributes. Until
# that state becomes session-owned, two solves in the same process must not run
# concurrently.
_SOLVER_LOCK = threading.RLock()


@contextmanager
def exclusive_solver_access(
    should_cancel: CancelCheck | None = None,
    *,
    poll_seconds: float = 0.1,
) -> Iterator[None]:
    """Serialize in-process solves while keeping lock acquisition cancellable."""
    poll = max(0.01, float(poll_seconds))
    acquired = False
    try:
        while not acquired:
            raise_if_cancelled(should_cancel)
            acquired = _SOLVER_LOCK.acquire(timeout=poll)
        raise_if_cancelled(should_cancel)
        yield
    finally:
        if acquired:
            _SOLVER_LOCK.release()
