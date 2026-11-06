"""Source-checkout profiler for the recorded random_005 Vert/scour workflow.

Run with python -m tools.profiling.profile_scour_workflow --model <model.hrx>.
The geometry constants below belong to that benchmark, not arbitrary HRX models.
"""
from __future__ import annotations

import argparse
import csv
import cProfile
import json
import os
import platform
import pstats
import shutil
import subprocess
import sys
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from histra.io.hr_loader import load_model
from histra.solver import AnalysisSession
from histra.solver.model_manager import ModelManager


try:
    import psutil
except ImportError:
    psutil = None


T = TypeVar("T")

MB = 1024.0 * 1024.0

PIER_X = 502.0
PIER_LENGTH = 139.8
PIER_Y = 0.0
PIER_WIDTH = 342.4

SOIL_REMOVED_MATERIAL_KEY = 147


@dataclass(slots=True)
class StageResult:
    name: str
    seconds: float
    rss_before_mb: float | None
    rss_after_mb: float | None
    rss_delta_mb: float | None
    peak_rss_mb: float | None
    process_cpu_seconds: float | None
    process_cpu_equivalent_cores: float | None
    process_cpu_mean_pct: float | None
    process_cpu_peak_pct: float | None
    system_cpu_mean_pct: float | None
    system_cpu_peak_pct: float | None
    external_cpu_estimate_pct: float | None
    available_memory_min_mb: float | None
    profile_file: str | None


_PROCESS = psutil.Process(os.getpid()) if psutil is not None else None


def current_rss_mb() -> float | None:
    """Return resident memory including NumPy/SciPy/native allocations."""
    if _PROCESS is None:
        return None
    return _PROCESS.memory_info().rss / MB


class ResourceSampler:
    """Sample RSS and CPU contention in a lightweight background thread.

    ``process_cpu_percent`` may exceed 100% for a multi-threaded process.  The
    system CPU samples are especially useful for spotting benchmark runs that
    were contaminated by unrelated applications.
    """

    def __init__(self, interval_seconds: float = 0.02) -> None:
        self.interval_seconds = interval_seconds
        self.peak_rss_mb: float | None = None
        self.available_memory_min_mb: float | None = None
        self.process_cpu_samples: list[float] = []
        self.system_cpu_samples: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        if _PROCESS is None or psutil is None:
            return

        rss = current_rss_mb()
        if rss is not None:
            self.peak_rss_mb = rss if self.peak_rss_mb is None else max(
                self.peak_rss_mb, rss
            )

        available = psutil.virtual_memory().available / MB
        self.available_memory_min_mb = (
            available
            if self.available_memory_min_mb is None
            else min(self.available_memory_min_mb, available)
        )

        self.process_cpu_samples.append(float(_PROCESS.cpu_percent(interval=None)))
        self.system_cpu_samples.append(float(psutil.cpu_percent(interval=None)))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    def __enter__(self) -> "ResourceSampler":
        if _PROCESS is None or psutil is None:
            return self

        # Prime psutil's delta-based CPU counters.  The first returned value is
        # intentionally discarded.
        _PROCESS.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None)

        # Capture memory immediately without adding a near-zero-duration CPU
        # sample that would bias the mean downward.
        rss = current_rss_mb()
        if rss is not None:
            self.peak_rss_mb = rss
        self.available_memory_min_mb = psutil.virtual_memory().available / MB

        self._thread = threading.Thread(
            target=self._run,
            name="histra-resource-profiler",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join()
        self._sample()

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _peak(values: list[float]) -> float | None:
        return max(values) if values else None

    @property
    def process_cpu_mean_pct(self) -> float | None:
        return self._mean(self.process_cpu_samples)

    @property
    def process_cpu_peak_pct(self) -> float | None:
        return self._peak(self.process_cpu_samples)

    @property
    def system_cpu_mean_pct(self) -> float | None:
        return self._mean(self.system_cpu_samples)

    @property
    def system_cpu_peak_pct(self) -> float | None:
        return self._peak(self.system_cpu_samples)


@dataclass(slots=True)
class UpdateDomainCall:
    stage: str
    stage_call_index: int
    global_call_index: int
    solver_step: int
    sampled: bool
    warmup: bool
    total_ns: int
    phase_ns: dict[str, int]
    runtime_counts: dict[str, int]


class UpdateDomainProfiler:
    """Opt-in deep timer for ``HystereticBatchRuntime.update_domain``.

    The production ``update_domain`` method is *not* reimplemented.  During a
    sampled call, this profiler temporarily wraps the exact module-level kernel
    dispatchers used by the production method.  Therefore the authoritative
    operation sequence and all numerical arithmetic remain unchanged.
    """

    ANALYSIS_STAGES = frozenset({"03_vert", "05_scour_1", "07_scour_2"})

    KERNEL_NAMES = (
        "_map_global_to_local",
        "_prepare_interface_kinematics",
        "_map_and_prepare_interface_kinematics",
        "_advance_and_evaluate_simple_linear_batch",
        "_advance_evaluate_and_finish_simple_linear_batch",
        "_advance_transverse_targets",
        "_evaluate_simple_linear_batch",
        "_evaluate_linear_batch",
        "_finish_transverse_batch",
        "_advance_interface_coulomb_targets",
        "_evaluate_initial_coulomb_batch",
        "_assemble_full_interface_forces",
        "_prepare_quad_kinematics",
        "_evaluate_quad_takeda_batch",
        "_refresh_global_resisting_force",
        "_refresh_global_resisting_force_by_dof",
        "_refresh_max_u_cache",
    )

    STATIC_PHASE_NAMES = {
        "_prepare_interface_kinematics": "02_interface_kinematics",
        "_map_and_prepare_interface_kinematics": (
            "01_02_interface_mapping_and_kinematics"
        ),
        "_advance_and_evaluate_simple_linear_batch": (
            "04_transverse_targets_and_constitutive_simple"
        ),
        "_advance_evaluate_and_finish_simple_linear_batch": (
            "04_05_transverse_update_and_force_reduction_simple"
        ),
        "_advance_transverse_targets": "03_transverse_targets",
        "_evaluate_simple_linear_batch": "04_transverse_constitutive_simple",
        "_evaluate_linear_batch": "04_transverse_constitutive_general",
        "_finish_transverse_batch": "05_transverse_force_reduction",
        "_advance_interface_coulomb_targets": "06_coulomb_targets",
        "_evaluate_initial_coulomb_batch": "07_coulomb_constitutive",
        "_assemble_full_interface_forces": "08_interface_force_assembly",
        "_prepare_quad_kinematics": "10_quad_kinematics",
        "_evaluate_quad_takeda_batch": "11_quad_constitutive",
        "_refresh_global_resisting_force": "12_global_resisting_force",
        "_refresh_global_resisting_force_by_dof": "12_global_resisting_force",
        "_refresh_max_u_cache": "13_max_u_cache",
    }

    def __init__(self, *, every: int = 1, warmup_calls: int = 3) -> None:
        if every < 1:
            raise ValueError("deep update-domain sampling interval must be >= 1")
        if warmup_calls < 0:
            raise ValueError("deep update-domain warmup must be >= 0")
        self.every = int(every)
        self.warmup_calls = int(warmup_calls)
        self.current_stage: str | None = None
        self.calls: list[UpdateDomainCall] = []
        self._stage_call_counts: dict[str, int] = defaultdict(int)
        self._global_call_count = 0
        self._module: Any | None = None
        self._runtime_class: Any | None = None
        self._original_update_domain: Callable[..., Any] | None = None
        self._original_kernels: dict[str, Callable[..., Any]] = {}
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        import histra.solver.hysteretic_batch as batch

        missing = [name for name in self.KERNEL_NAMES if not hasattr(batch, name)]
        if missing:
            raise RuntimeError(
                "Deep update-domain profiling requires the split-kernel "
                "hysteretic runtime. Missing: " + ", ".join(missing)
            )
        runtime_class = batch.HystereticBatchRuntime
        original_update = runtime_class.update_domain
        self._module = batch
        self._runtime_class = runtime_class
        self._original_update_domain = original_update
        self._original_kernels = {
            name: getattr(batch, name) for name in self.KERNEL_NAMES
        }

        profiler = self

        def profiled_update_domain(runtime: Any, x: Any, state: Any) -> Any:
            stage = profiler.current_stage or "outside_profiled_stage"
            profiler._global_call_count += 1
            profiler._stage_call_counts[stage] += 1
            global_index = profiler._global_call_count
            stage_index = profiler._stage_call_counts[stage]
            solver_step = int(getattr(state, "step", 0))

            sample_this_call = (
                stage in profiler.ANALYSIS_STAGES
                and ((stage_index - 1) % profiler.every == 0)
            )
            warmup = stage_index <= profiler.warmup_calls

            runtime_counts = {
                "transverse_springs": len(getattr(runtime, "springs", ())),
                "interfaces": len(getattr(runtime, "records", ())),
                "coulomb_springs": len(getattr(runtime, "coulomb_springs", ())),
                "quads": len(getattr(runtime, "quad_records", ())),
                "parameter_columns": int(
                    getattr(getattr(runtime, "_params", None), "shape", (0, 0))[1]
                ),
            }

            if not sample_this_call:
                start_ns = time.perf_counter_ns()
                try:
                    return original_update(runtime, x, state)
                finally:
                    profiler.calls.append(
                        UpdateDomainCall(
                            stage=stage,
                            stage_call_index=stage_index,
                            global_call_index=global_index,
                            solver_step=solver_step,
                            sampled=False,
                            warmup=warmup,
                            total_ns=time.perf_counter_ns() - start_ns,
                            phase_ns={},
                            runtime_counts=runtime_counts,
                        )
                    )

            assert profiler._module is not None
            phase_ns: dict[str, int] = defaultdict(int)
            kernel_invocations: dict[str, int] = defaultdict(int)
            installed_wrappers: dict[str, Callable[..., Any]] = {}

            for kernel_name, kernel in profiler._original_kernels.items():
                def timed_kernel(
                    *args: Any,
                    __kernel_name: str = kernel_name,
                    __kernel: Callable[..., Any] = kernel,
                    **kwargs: Any,
                ) -> Any:
                    invocation = kernel_invocations[__kernel_name]
                    kernel_invocations[__kernel_name] += 1
                    phase_name = profiler._phase_name(__kernel_name, invocation)
                    kernel_start_ns = time.perf_counter_ns()
                    try:
                        return __kernel(*args, **kwargs)
                    finally:
                        phase_ns[phase_name] += (
                            time.perf_counter_ns() - kernel_start_ns
                        )

                installed_wrappers[kernel_name] = timed_kernel
                setattr(profiler._module, kernel_name, timed_kernel)

            start_ns = time.perf_counter_ns()
            try:
                return original_update(runtime, x, state)
            finally:
                total_ns = time.perf_counter_ns() - start_ns
                # Restore the exact production dispatchers before recording or
                # doing any file/report work.
                for kernel_name, kernel in profiler._original_kernels.items():
                    setattr(profiler._module, kernel_name, kernel)

                kernel_total_ns = sum(phase_ns.values())
                phase_ns["99_python_dispatch_and_timer_overhead"] += max(
                    0, total_ns - kernel_total_ns
                )
                profiler.calls.append(
                    UpdateDomainCall(
                        stage=stage,
                        stage_call_index=stage_index,
                        global_call_index=global_index,
                        solver_step=solver_step,
                        sampled=True,
                        warmup=warmup,
                        total_ns=total_ns,
                        phase_ns=dict(phase_ns),
                        runtime_counts=runtime_counts,
                    )
                )

        runtime_class.update_domain = profiled_update_domain
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        assert self._runtime_class is not None
        assert self._original_update_domain is not None
        self._runtime_class.update_domain = self._original_update_domain
        if self._module is not None:
            for kernel_name, kernel in self._original_kernels.items():
                setattr(self._module, kernel_name, kernel)
        self._installed = False

    def _phase_name(self, kernel_name: str, invocation: int) -> str:
        if kernel_name == "_map_global_to_local":
            if invocation == 0:
                return "01_interface_map_global_to_local"
            if invocation == 1:
                return "09_quad_map_global_to_local"
            return f"09b_extra_map_global_to_local_{invocation + 1}"
        return self.STATIC_PHASE_NAMES.get(kernel_name, kernel_name)

    def write_reports(self, output_dir: Path) -> None:
        if not self.calls:
            return

        self._write_calls_csv(output_dir / "update_domain_calls.csv")
        breakdown = self._build_breakdown()
        self._write_breakdown_csv(
            output_dir / "update_domain_breakdown.csv", breakdown
        )
        with (output_dir / "update_domain_breakdown.json").open(
            "w", encoding="utf-8"
        ) as stream:
            json.dump(breakdown, stream, indent=2)
        self._write_text_report(
            output_dir / "update_domain_breakdown.txt", breakdown
        )

    def _analysis_calls(self) -> list[UpdateDomainCall]:
        return [call for call in self.calls if call.stage in self.ANALYSIS_STAGES]

    def _write_calls_csv(self, path: Path) -> None:
        phase_names = sorted(
            {
                phase
                for call in self.calls
                for phase in call.phase_ns
            }
        )
        fieldnames = [
            "stage", "stage_call_index", "global_call_index", "solver_step",
            "sampled", "warmup", "total_ms", "kernel_sum_ms", "unattributed_ms",
            "transverse_springs", "interfaces", "coulomb_springs", "quads",
            "parameter_columns",
            *[f"phase_ms:{phase}" for phase in phase_names],
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for call in self.calls:
                row: dict[str, Any] = {
                    "stage": call.stage,
                    "stage_call_index": call.stage_call_index,
                    "global_call_index": call.global_call_index,
                    "solver_step": call.solver_step,
                    "sampled": call.sampled,
                    "warmup": call.warmup,
                    "total_ms": call.total_ns / 1.0e6,
                    "kernel_sum_ms": sum(
                        value
                        for phase, value in call.phase_ns.items()
                        if not phase.startswith("99_")
                    ) / 1.0e6,
                    "unattributed_ms": call.phase_ns.get(
                        "99_python_dispatch_and_timer_overhead", 0
                    ) / 1.0e6,
                    **call.runtime_counts,
                }
                for phase in phase_names:
                    row[f"phase_ms:{phase}"] = call.phase_ns.get(phase, 0) / 1.0e6
                writer.writerow(row)

    @staticmethod
    def _percentile(values: list[float], q: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        position = (len(ordered) - 1) * q
        lo = int(position)
        hi = min(lo + 1, len(ordered) - 1)
        fraction = position - lo
        return ordered[lo] * (1.0 - fraction) + ordered[hi] * fraction

    @classmethod
    def _stats_ms(cls, values_ns: list[int]) -> dict[str, float | int | None]:
        values_ms = [value / 1.0e6 for value in values_ns]
        if not values_ms:
            return {
                "count": 0,
                "total_ms": 0.0,
                "mean_ms": None,
                "median_ms": None,
                "p95_ms": None,
                "min_ms": None,
                "max_ms": None,
            }
        ordered = sorted(values_ms)
        return {
            "count": len(values_ms),
            "total_ms": sum(values_ms),
            "mean_ms": sum(values_ms) / len(values_ms),
            "median_ms": cls._percentile(values_ns, 0.50) / 1.0e6,
            "p95_ms": cls._percentile(values_ns, 0.95) / 1.0e6,
            "min_ms": ordered[0],
            "max_ms": ordered[-1],
        }

    def _build_breakdown(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sampling_every": self.every,
            "warmup_calls_per_stage": self.warmup_calls,
            "note": (
                "Phase timers wrap the exact production kernel dispatchers. "
                "The 99_ phase is residual Python dispatch plus timer-wrapper "
                "overhead; it is not purely application Python time."
            ),
            "stages": {},
        }

        for stage in sorted(self.ANALYSIS_STAGES):
            stage_calls = [call for call in self.calls if call.stage == stage]
            if not stage_calls:
                continue
            sampled = [call for call in stage_calls if call.sampled]
            steady = [call for call in sampled if not call.warmup]
            selected = steady or sampled
            total_update_ns = [call.total_ns for call in stage_calls]
            sampled_total_ns = [call.total_ns for call in selected]
            phase_names = sorted(
                {phase for call in selected for phase in call.phase_ns}
            )
            phase_rows: list[dict[str, Any]] = []
            for phase in phase_names:
                values = [call.phase_ns.get(phase, 0) for call in selected]
                stats = self._stats_ms(values)
                mean_ms = stats["mean_ms"]
                estimated_total_s = (
                    float(mean_ms) * len(stage_calls) / 1000.0
                    if mean_ms is not None else 0.0
                )
                selected_update_stats = self._stats_ms(sampled_total_ns)
                selected_update_mean_ms = selected_update_stats["mean_ms"]
                phase_rows.append(
                    {
                        "phase": phase,
                        **stats,
                        "estimated_stage_total_s": estimated_total_s,
                        "estimated_share_of_update_domain_pct": (
                            100.0 * float(mean_ms) / float(selected_update_mean_ms)
                            if mean_ms is not None
                            and selected_update_mean_ms not in (None, 0.0)
                            else 0.0
                        ),
                    }
                )

            result["stages"][stage] = {
                "total_update_domain_calls": len(stage_calls),
                "sampled_calls": len(sampled),
                "steady_sampled_calls": len(steady),
                "update_domain_all_calls": self._stats_ms(total_update_ns),
                "update_domain_selected_sampled_calls": self._stats_ms(sampled_total_ns),
                "runtime_counts_first_call": stage_calls[0].runtime_counts,
                "phases": phase_rows,
            }
        return result

    @staticmethod
    def _write_breakdown_csv(path: Path, breakdown: dict[str, Any]) -> None:
        fieldnames = [
            "stage", "phase", "total_update_domain_calls", "sampled_calls",
            "steady_sampled_calls", "count", "total_ms", "mean_ms",
            "median_ms", "p95_ms", "min_ms", "max_ms",
            "estimated_stage_total_s", "estimated_share_of_update_domain_pct",
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for stage, stage_data in breakdown["stages"].items():
                for phase in stage_data["phases"]:
                    writer.writerow(
                        {
                            "stage": stage,
                            "total_update_domain_calls": stage_data[
                                "total_update_domain_calls"
                            ],
                            "sampled_calls": stage_data["sampled_calls"],
                            "steady_sampled_calls": stage_data[
                                "steady_sampled_calls"
                            ],
                            **phase,
                        }
                    )

    @staticmethod
    def _write_text_report(path: Path, breakdown: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as stream:
            stream.write("DEEP update_domain BREAKDOWN\n")
            stream.write("=" * 88 + "\n")
            stream.write(breakdown["note"] + "\n")
            stream.write(
                f"Sampling every {breakdown['sampling_every']} call(s); "
                f"warmup={breakdown['warmup_calls_per_stage']} call(s)/stage.\n\n"
            )
            for stage, stage_data in breakdown["stages"].items():
                all_stats = stage_data["update_domain_all_calls"]
                stream.write(f"{stage}\n")
                stream.write("-" * 88 + "\n")
                stream.write(
                    f"calls={stage_data['total_update_domain_calls']}  "
                    f"sampled={stage_data['sampled_calls']}  "
                    f"steady_samples={stage_data['steady_sampled_calls']}  "
                    f"update total={all_stats['total_ms'] / 1000.0:.3f} s  "
                    f"mean={all_stats['mean_ms']:.3f} ms/call\n"
                )
                counts = stage_data["runtime_counts_first_call"]
                stream.write(
                    "runtime: " + ", ".join(
                        f"{key}={value}" for key, value in counts.items()
                    ) + "\n\n"
                )
                stream.write(
                    f"{'phase':<42}{'mean ms':>11}{'p95 ms':>11}"
                    f"{'est total s':>14}{'share %':>10}\n"
                )
                for phase in stage_data["phases"]:
                    stream.write(
                        f"{phase['phase']:<42}"
                        f"{phase['mean_ms']:>11.4f}"
                        f"{phase['p95_ms']:>11.4f}"
                        f"{phase['estimated_stage_total_s']:>14.3f}"
                        f"{phase['estimated_share_of_update_domain_pct']:>10.1f}\n"
                    )
                stream.write("\n")


def _centre(interface) -> tuple[float, float, float]:
    vertices = interface.vint3d
    return tuple(
        sum(getattr(vertex, axis) for vertex in vertices) / 4.0
        for axis in ("x", "y", "z")
    )


def upstream_interface_keys(model, delta: float) -> list[int]:
    """Resolve the C# pier_1 upstream-scour region after preprocessing."""

    left = PIER_X - PIER_LENGTH / 2.0
    right = PIER_X + PIER_LENGTH / 2.0

    upstream = PIER_Y - PIER_WIDTH / 2.0
    limit = upstream + PIER_WIDTH * float(delta)

    selected: list[int] = []

    for interface in model.collections.interfaces.values():
        if "Restraint" not in (
            interface.parent_type_element1,
            interface.parent_type_element2,
        ):
            continue

        x, y, _ = _centre(interface)

        if (
            left - 1e-4 <= x <= right + 1e-4
            and upstream - 1e-4 <= y <= limit + 1e-4
        ):
            selected.append(int(interface.key))

    return sorted(selected)


def write_profile_report(
    profile_path: Path,
    output_path: Path,
    *,
    top_n: int = 80,
) -> None:
    """Write human-readable cumulative and self-time reports."""

    with output_path.open("w", encoding="utf-8") as stream:
        stream.write("=== SORTED BY CUMULATIVE TIME ===\n\n")

        stats = pstats.Stats(str(profile_path), stream=stream)
        stats.strip_dirs()
        stats.sort_stats(pstats.SortKey.CUMULATIVE)
        stats.print_stats(top_n)

        stream.write("\n\n")
        stream.write("=== SORTED BY SELF TIME ===\n\n")

        stats = pstats.Stats(str(profile_path), stream=stream)
        stats.strip_dirs()
        stats.sort_stats(pstats.SortKey.TIME)
        stats.print_stats(top_n)


def run_stage(
    name: str,
    operation: Callable[[], T],
    *,
    output_dir: Path,
    enable_cprofile: bool,
    memory_sample_interval: float,
    top_n: int,
) -> tuple[T, StageResult, Path | None]:

    print(f"\n{'=' * 80}")
    print(f"STAGE: {name}")
    print(f"{'=' * 80}")

    rss_before = current_rss_mb()
    sampler = ResourceSampler(memory_sample_interval)

    profiler = cProfile.Profile() if enable_cprofile else None

    value: T | None = None
    caught_exception: BaseException | None = None

    cpu_before = None
    if _PROCESS is not None:
        cpu_times = _PROCESS.cpu_times()
        cpu_before = float(cpu_times.user + cpu_times.system)

    start = time.perf_counter()

    try:
        with sampler:
            if profiler is not None:
                profiler.enable()

            try:
                value = operation()
            finally:
                if profiler is not None:
                    profiler.disable()

    except BaseException as exc:
        caught_exception = exc

    elapsed = time.perf_counter() - start
    rss_after = current_rss_mb()
    process_cpu_seconds = None
    process_cpu_equivalent_cores = None
    if _PROCESS is not None and cpu_before is not None:
        cpu_times = _PROCESS.cpu_times()
        cpu_after = float(cpu_times.user + cpu_times.system)
        process_cpu_seconds = max(0.0, cpu_after - cpu_before)
        if elapsed > 0.0:
            process_cpu_equivalent_cores = process_cpu_seconds / elapsed

    if rss_before is not None and rss_after is not None:
        rss_delta = rss_after - rss_before
    else:
        rss_delta = None

    profile_path: Path | None = None

    if profiler is not None:
        profile_path = output_dir / f"{name}.prof"
        report_path = output_dir / f"{name}.txt"

        profiler.dump_stats(str(profile_path))

        write_profile_report(
            profile_path,
            report_path,
            top_n=top_n,
        )

    external_cpu_estimate_pct = None
    if (
        psutil is not None
        and sampler.system_cpu_mean_pct is not None
        and sampler.process_cpu_mean_pct is not None
    ):
        logical_cpus = psutil.cpu_count(logical=True) or 1
        # psutil process CPU uses 100% == one fully used logical CPU, whereas
        # system CPU is already normalized over all logical CPUs.  Subtract the
        # process contribution to estimate background/other-process CPU load.
        process_system_equivalent = sampler.process_cpu_mean_pct / logical_cpus
        external_cpu_estimate_pct = max(
            0.0, sampler.system_cpu_mean_pct - process_system_equivalent
        )

    result = StageResult(
        name=name,
        seconds=elapsed,
        rss_before_mb=rss_before,
        rss_after_mb=rss_after,
        rss_delta_mb=rss_delta,
        peak_rss_mb=sampler.peak_rss_mb,
        process_cpu_seconds=process_cpu_seconds,
        process_cpu_equivalent_cores=process_cpu_equivalent_cores,
        process_cpu_mean_pct=sampler.process_cpu_mean_pct,
        process_cpu_peak_pct=sampler.process_cpu_peak_pct,
        system_cpu_mean_pct=sampler.system_cpu_mean_pct,
        system_cpu_peak_pct=sampler.system_cpu_peak_pct,
        external_cpu_estimate_pct=external_cpu_estimate_pct,
        available_memory_min_mb=sampler.available_memory_min_mb,
        profile_file=profile_path.name if profile_path else None,
    )

    print(f"Time:       {elapsed:10.3f} s")

    if rss_before is not None:
        print(f"RSS before: {rss_before:10.1f} MB")
        print(f"RSS after:  {rss_after:10.1f} MB")
        print(f"RSS delta:  {rss_delta:+10.1f} MB")
        print(f"Peak RSS:   {sampler.peak_rss_mb:10.1f} MB")
        if sampler.system_cpu_mean_pct is not None:
            print(
                f"System CPU: {sampler.system_cpu_mean_pct:10.1f}% mean / "
                f"{sampler.system_cpu_peak_pct:5.1f}% peak"
            )
            print(
                f"Process CPU:{sampler.process_cpu_mean_pct:10.1f}% mean / "
                f"{sampler.process_cpu_peak_pct:5.1f}% peak"
            )
            if process_cpu_equivalent_cores is not None:
                print(
                    f"CPU time:   {process_cpu_seconds:10.3f} s "
                    f"({process_cpu_equivalent_cores:.2f} core-equivalents)"
                )
            if external_cpu_estimate_pct is not None:
                print(
                    f"Other CPU*: {external_cpu_estimate_pct:10.1f}% estimated "
                    "aggregate system load"
                )
    else:
        print("RSS/CPU:    unavailable (install psutil)")

    if caught_exception is not None:
        raise caught_exception

    assert value is not None or operation is not None
    return value, result, profile_path


def combine_profiles(
    profile_paths: list[Path],
    output_path: Path,
) -> None:
    if not profile_paths:
        return

    combined = pstats.Stats(str(profile_paths[0]))

    for profile_path in profile_paths[1:]:
        combined.add(str(profile_path))

    combined.dump_stats(str(output_path))


def find_dot() -> str | None:
    dot = shutil.which("dot")

    if dot:
        return dot

    windows_default = Path(
        r"C:\Program Files\Graphviz\bin\dot.exe"
    )

    if windows_default.exists():
        return str(windows_default)

    return None


def find_gprof2dot_command() -> list[str] | None:
    executable = shutil.which("gprof2dot")

    if executable:
        return [executable]

    try:
        import gprof2dot  # noqa: F401
    except ImportError:
        return None

    return [sys.executable, "-m", "gprof2dot"]


def render_svg(
    profile_path: Path,
    svg_path: Path,
) -> bool:

    gprof2dot_command = find_gprof2dot_command()
    dot = find_dot()

    if gprof2dot_command is None:
        print("gprof2dot not found; skipping SVG generation.")
        return False

    if dot is None:
        print("Graphviz 'dot' not found; skipping SVG generation.")
        return False

    graph = subprocess.run(
        [
            *gprof2dot_command,
            "-f",
            "pstats",
            str(profile_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    subprocess.run(
        [
            dot,
            "-Tsvg",
            "-o",
            str(svg_path),
        ],
        input=graph.stdout,
        check=True,
    )

    return True



def _safe_package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


def _git_metadata() -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        data["root"] = root
        data["commit"] = subprocess.check_output(
            ["git", "-C", root, "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", root, "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        data["dirty"] = bool(status.strip())
    except Exception:
        data["available"] = False
    return data


def collect_environment_metadata() -> dict[str, Any]:
    data: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version,
        "python_executable": sys.executable,
        "command_line": sys.argv,
        "pid": os.getpid(),
        "packages": {
            name: _safe_package_version(name)
            for name in ("numpy", "scipy", "numba", "psutil")
        },
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
        "git": _git_metadata(),
    }

    if psutil is not None:
        data["cpu_logical"] = psutil.cpu_count(logical=True)
        data["cpu_physical"] = psutil.cpu_count(logical=False)
        data["total_memory_mb"] = psutil.virtual_memory().total / MB
        try:
            freq = psutil.cpu_freq()
            if freq is not None:
                data["cpu_frequency_mhz"] = {
                    "current": freq.current,
                    "min": freq.min,
                    "max": freq.max,
                }
        except Exception:
            pass
        if _PROCESS is not None and hasattr(_PROCESS, "cpu_affinity"):
            try:
                data["cpu_affinity"] = _PROCESS.cpu_affinity()
            except Exception:
                pass

    try:
        import numba
        data["numba_runtime_threads"] = int(numba.get_num_threads())
        data["numba_config_threads"] = int(numba.config.NUMBA_NUM_THREADS)
    except Exception:
        pass

    try:
        from threadpoolctl import threadpool_info
        data["native_threadpools"] = threadpool_info()
    except Exception:
        pass
    return data


def write_summary(
    output_dir: Path,
    *,
    model_path: Path,
    model,
    scour_1_keys: list[int],
    scour_2_keys: list[int],
    stages: list[StageResult],
) -> None:

    metadata = {
        "model": str(model_path.resolve()),
        "python": sys.version,
        "gdl": int(getattr(model, "gdl", 0)),
        "quads": len(model.collections.quads),
        "interfaces": len(model.collections.interfaces),
        "scour_1_interface_count": len(scour_1_keys),
        "scour_2_interface_count": len(scour_2_keys),
        "new_interfaces_in_scour_2": len(
            set(scour_2_keys) - set(scour_1_keys)
        ),
        "psutil_available": psutil is not None,
        "environment": collect_environment_metadata(),
        "stages": [asdict(stage) for stage in stages],
    }

    with (output_dir / "summary.json").open(
        "w",
        encoding="utf-8",
    ) as stream:
        json.dump(
            metadata,
            stream,
            indent=2,
        )

    with (output_dir / "summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(StageResult.__dataclass_fields__),
        )

        writer.writeheader()

        for stage in stages:
            writer.writerow(asdict(stage))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Profile the HiStrA Vert/scour workflow."
    )

    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="HRX for the recorded random_005 pier/scour geometry.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory. Defaults to profiles/<timestamp>.",
    )

    parser.add_argument(
        "--solver-logs",
        action="store_true",
        help="Print AnalysisSession logs while profiling.",
    )

    parser.add_argument(
        "--timing-only",
        action="store_true",
        help=(
            "Disable cProfile and record only wall time/RSS. "
            "Useful for cleaner final benchmarks."
        ),
    )

    parser.add_argument(
        "--no-svg",
        action="store_true",
    )

    parser.add_argument(
        "--memory-sample-ms",
        type=float,
        default=20.0,
    )

    parser.add_argument(
        "--top",
        type=int,
        default=80,
        help="Number of functions in each text profile report.",
    )


    parser.add_argument(
        "--deep-update-domain",
        action="store_true",
        help=(
            "Time the internal kernels called by HystereticBatchRuntime."
            "update_domain without changing solver arithmetic."
        ),
    )

    parser.add_argument(
        "--deep-update-domain-every",
        type=int,
        default=1,
        help=(
            "Deep-time every Nth update_domain call (default: 1 = every call). "
            "Use a larger value if you want lower instrumentation overhead."
        ),
    )

    parser.add_argument(
        "--deep-update-domain-warmup",
        type=int,
        default=3,
        help=(
            "Number of first update_domain calls per analysis stage kept in "
            "the raw CSV but excluded from steady-state phase statistics."
        ),
    )

    args = parser.parse_args()

    model_path = args.model.resolve()

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model does not exist: {model_path}"
        )

    if args.output is None:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_dir = Path("profiles") / timestamp
    else:
        output_dir = args.output

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    enable_cprofile = not args.timing_only
    memory_interval = args.memory_sample_ms / 1000.0

    stages: list[StageResult] = []
    profile_paths: list[Path] = []

    update_domain_profiler: UpdateDomainProfiler | None = None
    if args.deep_update_domain:
        update_domain_profiler = UpdateDomainProfiler(
            every=args.deep_update_domain_every,
            warmup_calls=args.deep_update_domain_warmup,
        )
        update_domain_profiler.install()
        if enable_cprofile:
            print(
                "NOTE: deep update_domain timing is enabled together with cProfile. "
                "For the cleanest kernel timings, rerun with --timing-only."
            )

    def execute_stage(name: str, operation: Callable[[], T]) -> T:
        if update_domain_profiler is not None:
            update_domain_profiler.current_stage = name
        try:
            value, result, profile_path = run_stage(
                name,
                operation,
                output_dir=output_dir,
                enable_cprofile=enable_cprofile,
                memory_sample_interval=memory_interval,
                top_n=args.top,
            )
        finally:
            if update_domain_profiler is not None:
                update_domain_profiler.current_stage = None

        stages.append(result)

        if profile_path is not None:
            profile_paths.append(profile_path)

        return value

    model = execute_stage(
        "00_load_model",
        lambda: load_model(model_path),
    )

    execute_stage(
        "01_prepare_model",
        lambda: ModelManager.prepare_model(model),
    )

    scour_1_keys, scour_2_keys = execute_stage(
        "02_resolve_scour_interfaces",
        lambda: (
            upstream_interface_keys(model, 0.2),
            upstream_interface_keys(model, 0.4),
        ),
    )

    print()
    print(f"Scour 0.2 interfaces: {len(scour_1_keys)}")
    print(f"Scour 0.4 interfaces: {len(scour_2_keys)}")
    print(
        "Additional interfaces at 0.4: "
        f"{len(set(scour_2_keys) - set(scour_1_keys))}"
    )

    def on_log(text: str) -> None:
        if args.solver_logs:
            print(
                f"[{model_path.parent.name}] {text}",
                flush=True,
            )

    session = AnalysisSession(
        model,
        on_log=on_log,
    )

    execute_stage(
        "03_vert",
        lambda: session.run("Vert"),
    )

    execute_stage(
        "04_change_materials_0p2",
        lambda: session.change_interface_materials(
            scour_1_keys,
            SOIL_REMOVED_MATERIAL_KEY,
        ),
    )

    execute_stage(
        "05_scour_1",
        lambda: session.run("scour_1"),
    )

    execute_stage(
        "06_change_materials_0p4",
        lambda: session.change_interface_materials(
            scour_2_keys,
            SOIL_REMOVED_MATERIAL_KEY,
        ),
    )

    execute_stage(
        "07_scour_2",
        lambda: session.run("scour_2"),
    )

    if update_domain_profiler is not None:
        update_domain_profiler.uninstall()
        update_domain_profiler.write_reports(output_dir)

    write_summary(
        output_dir,
        model_path=model_path,
        model=model,
        scour_1_keys=scour_1_keys,
        scour_2_keys=scour_2_keys,
        stages=stages,
    )

    if profile_paths:
        combined_profile = output_dir / "profile.prof"

        combine_profiles(
            profile_paths,
            combined_profile,
        )

        write_profile_report(
            combined_profile,
            output_dir / "profile.txt",
            top_n=args.top,
        )

        if not args.no_svg:
            svg_path = output_dir / "profile.svg"

            if render_svg(
                combined_profile,
                svg_path,
            ):
                print(f"\nSVG written to: {svg_path}")

    print("\n")
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for stage in stages:
        peak = (
            f"{stage.peak_rss_mb:.1f} MB"
            if stage.peak_rss_mb is not None
            else "n/a"
        )

        cpu_text = (
            f"   sys CPU: {stage.system_cpu_mean_pct:.0f}%"
            if stage.system_cpu_mean_pct is not None
            else ""
        )
        if stage.external_cpu_estimate_pct is not None:
            cpu_text += f"   other*: {stage.external_cpu_estimate_pct:.0f}%"
        print(
            f"{stage.name:<32}"
            f"{stage.seconds:>10.3f} s"
            f"   peak RSS: {peak}"
            f"{cpu_text}"
        )

    total_seconds = sum(stage.seconds for stage in stages)

    peak_values = [
        stage.peak_rss_mb
        for stage in stages
        if stage.peak_rss_mb is not None
    ]

    print("-" * 80)
    print(f"{'Total staged time':<32}{total_seconds:>10.3f} s")

    if peak_values:
        print(
            f"{'Maximum observed RSS':<32}"
            f"{max(peak_values):>10.1f} MB"
        )

    print()
    print(f"Results written to: {output_dir.resolve()}")
    if update_domain_profiler is not None:
        print("Deep update_domain reports:")
        for filename in (
            "update_domain_breakdown.txt",
            "update_domain_breakdown.csv",
            "update_domain_breakdown.json",
            "update_domain_calls.csv",
        ):
            print(f"  - {output_dir / filename}")


if __name__ == "__main__":
    main()
