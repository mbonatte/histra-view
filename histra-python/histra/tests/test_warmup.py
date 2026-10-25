from __future__ import annotations

import time
from histra import warmup_compiled_backends


def test_warmup_compiled_backends_executes_cleanly():
    # Calling warmup should run without raising any error
    warmup_compiled_backends(verbose=True)

    # Subsequent call should be fast (warm / cached)
    t0 = time.perf_counter()
    warmup_compiled_backends(verbose=True)
    t1 = time.perf_counter()

    assert (t1 - t0) < 0.05
