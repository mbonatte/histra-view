"""Process resource settings for a single large solve.

Native BLAS search paths must be selected before the child interpreter starts;
changing LD_LIBRARY_PATH after ctypes has loaded SuiteSparse cannot switch BLAS.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


@dataclass(frozen=True)
class SolverResources:
    """Independent thread budgets for element kernels and sparse-factor BLAS."""

    kernel_threads: int = 8
    blas_threads: int = 4
    blas_directory: str | Path | None = None
    linear_solver_backend: str = "auto"

    def environment(self, base: dict[str, str] | None = None) -> dict[str, str]:
        environment = dict(os.environ if base is None else base)
        cores = available_cpu_count()
        kernels = _thread_count(self.kernel_threads, cores, "kernel_threads")
        blas = _thread_count(self.blas_threads, cores, "blas_threads")
        for name in ("NUMBA_NUM_THREADS", "HISTRA_NUMBA_THREADS", "OMP_NUM_THREADS"):
            environment[name] = str(kernels)
        for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS"):
            environment[name] = str(blas)
        backend = self.linear_solver_backend.strip().lower()
        if backend not in {"auto", "umfpack", "superlu", "cholmod", "cudss"}:
            raise ValueError("Unsupported linear_solver_backend")
        environment["HISTRA_LINEAR_SOLVER"] = backend
        directory = self.blas_directory or discover_openblas_directory()
        if directory is not None:
            _set_blas_directory(environment, Path(directory))
        return environment


def available_cpu_count() -> int:
    return len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)


def _thread_count(value: int, cores: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return min(value, cores)


def discover_openblas_directory() -> Path | None:
    """Find the optional project-local Ubuntu OpenBLAS runtime."""
    directory = Path(sys.prefix) / "native/openblas/usr/lib/x86_64-linux-gnu/openblas-pthread"
    return directory if _is_blas_directory(directory) else None


def _is_blas_directory(directory: Path) -> bool:
    return all((directory / name).is_file() for name in ("libblas.so.3", "liblapack.so.3", "libopenblas.so.0"))


def _set_blas_directory(environment: dict[str, str], directory: Path) -> None:
    if not sys.platform.startswith("linux"):
        raise ValueError("Selecting a native BLAS directory currently requires Linux")
    directory = directory.resolve()
    if not _is_blas_directory(directory):
        raise ValueError(f"No complete LP64 OpenBLAS runtime in {directory}")
    previous = environment.get("LD_LIBRARY_PATH", "")
    environment["LD_LIBRARY_PATH"] = str(directory) + (os.pathsep + previous if previous else "")


def inspect_process_resources() -> dict[str, object]:
    """Describe actual loaded native libraries, rather than only requested knobs."""
    libraries: set[str] = set()
    maps = Path("/proc/self/maps")
    if maps.exists():
        for line in maps.read_text().splitlines():
            path = line.split()[-1]
            if path.startswith("/") and any(name in path.lower() for name in ("blas", "lapack", "umfpack", "cholmod", "cudss")):
                libraries.add(path)
    return {"available_cpus": available_cpu_count(), "kernel_threads": os.environ.get("HISTRA_NUMBA_THREADS"),
            "blas_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
            "native_blas": _native_blas_details(), "native_libraries": sorted(libraries)}


def validate_native_blas() -> None:
    """Reject an ILP64 runtime before passing SuiteSparse's 32-bit BLAS integers."""
    import ctypes

    directory = os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)[0]
    library = Path(directory) / "libopenblas.so.0"
    if not directory or not library.is_file():
        return
    native = ctypes.CDLL(str(library))
    config = native.openblas_get_config
    config.restype = ctypes.c_char_p
    if b"USE64BITINT" in config():
        raise ValueError("SuiteSparse requires LP64 OpenBLAS; the selected runtime uses ILP64")


def _native_blas_details() -> dict[str, object] | None:
    import ctypes

    directory = os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)[0]
    library = Path(directory) / "libopenblas.so.0"
    if not directory or not library.is_file():
        return None
    native = ctypes.CDLL(str(library))
    native.openblas_get_config.restype = ctypes.c_char_p
    native.openblas_get_num_threads.restype = ctypes.c_int
    return {"config": native.openblas_get_config().decode(),
            "threads": native.openblas_get_num_threads()}
