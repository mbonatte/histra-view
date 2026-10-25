"""Lossless nonlinear solver-state snapshots.

Snapshots deliberately mutate existing arrays/objects on restore so aliases
(``Program.u``, integrator ``u``, and ``ModelManager._u_total``) remain valid.
They cover the translated element/spring set and fail explicitly for state that
cannot be copied.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from functools import lru_cache
import hashlib
import pickle
from typing import Any, Iterable
from enum import Enum

import numpy as np

from histra.solver.model_manager import ModelManager

# Exact built-in scalar types dominate nonlinear spring state.  Using a set of
# exact types avoids the comparatively expensive recursive ``isinstance`` path
# for every scalar in every spring dictionary.  Enum values remain immutable,
# but need a separate ``isinstance`` check because each enum has its own type.
_IMMUTABLE_SCALAR_TYPES = {
    type(None),
    bool,
    int,
    float,
    complex,
    str,
    bytes,
}
_MISSING = object()


def _is_immutable_scalar(value: Any) -> bool:
    return type(value) in _IMMUTABLE_SCALAR_TYPES or isinstance(value, Enum)


def _copy_list(value: list[Any]) -> list[Any]:
    """Copy a list while fast-pathing the short numeric lists used by springs."""
    if not value:
        return []
    if all(_is_immutable_scalar(item) for item in value):
        return value.copy()
    return [_copy_array(item) for item in value]


def _copy_tuple(value: tuple[Any, ...]) -> tuple[Any, ...]:
    """Return immutable scalar tuples directly; recursively copy other tuples."""
    if not value or all(_is_immutable_scalar(item) for item in value):
        return value
    return tuple(_copy_array(item) for item in value)




def _copy_array(value: Any) -> Any:
    """Fast value copy for solver state.

    Nonlinear snapshots contain thousands of spring dictionaries made almost
    entirely of scalars and short numeric containers.  ``deepcopy`` on each
    complete dictionary creates large memo/GC workloads and can cause very
    long pauses in multi-step ArcLength runs.  Copy the supported state shapes
    directly and retain ``deepcopy`` only as an explicit fallback.
    """
    value_type = type(value)
    if value_type in _IMMUTABLE_SCALAR_TYPES or isinstance(value, Enum):
        return value
    if isinstance(value, np.ndarray):
        return value.copy()
    if value_type is list:
        return _copy_list(value)
    if value_type is tuple:
        return _copy_tuple(value)
    if value_type is dict:
        return _copy_state_dict(value)
    if value_type is set:
        return {_copy_array(item) for item in value}
    return deepcopy(value)


def _copy_state_dict(values: dict[str, Any]) -> dict[str, Any]:
    """Copy an object state dictionary with an inlined common-type dispatch.

    Calling ``_copy_array`` for every scalar was the dominant overhead in
    snapshots containing many unmanaged springs.  This loop preserves the
    exact copied values but handles scalars, arrays, and short scalar lists
    without an additional Python function call per field.
    """
    copied: dict[str, Any] = {}
    for key, value in values.items():
        value_type = type(value)
        if value_type in _IMMUTABLE_SCALAR_TYPES or isinstance(value, Enum):
            copied[key] = value
        elif isinstance(value, np.ndarray):
            copied[key] = value.copy()
        elif value_type is list:
            copied[key] = _copy_list(value)
        elif value_type is tuple:
            copied[key] = _copy_tuple(value)
        elif value_type is dict:
            copied[key] = _copy_state_dict(value)
        elif value_type is set:
            copied[key] = {_copy_array(item) for item in value}
        else:
            copied[key] = deepcopy(value)
    return copied


def _restore_array(target: Any, saved: Any) -> Any:
    """Restore one saved value without making an unnecessary second snapshot."""
    if isinstance(target, np.ndarray) and isinstance(saved, np.ndarray):
        if target.shape == saved.shape:
            target[...] = saved
            return target
        return saved.copy()

    target_type = type(target)
    saved_type = type(saved)
    if target_type is list and saved_type is list:
        if not saved or all(_is_immutable_scalar(item) for item in saved):
            target[:] = saved
        else:
            target[:] = [_copy_array(item) for item in saved]
        return target
    if target_type is dict and saved_type is dict:
        _restore_state_dict(target, saved)
        return target
    if target_type is set and saved_type is set:
        target.clear()
        target.update(_copy_array(item) for item in saved)
        return target
    return _copy_array(saved)



@lru_cache(maxsize=None)
def _dataclass_state_fields(cls: type[Any]) -> tuple[str, ...]:
    """Return the fixed dataclass field names for a solver object type.

    Spring classes use slots for their fixed numerical schema.  Their
    ``__dict__`` therefore contains only optional dynamic overrides and is no
    longer a complete representation of constitutive state.  Cache the field
    names per class so snapshots can copy the complete state without repeating
    dataclass introspection for every spring.
    """
    return tuple(field.name for field in fields(cls))


def _copy_object_state(obj: Any) -> dict[str, Any]:
    """Copy fixed dataclass fields plus any genuinely dynamic attributes."""
    copied: dict[str, Any] = {}
    if is_dataclass(obj):
        for key in _dataclass_state_fields(type(obj)):
            if hasattr(obj, key):
                copied[key] = _copy_array(getattr(obj, key))

    dynamic = getattr(obj, "__dict__", None)
    if dynamic:
        for key, value in dynamic.items():
            if key not in copied:
                copied[key] = _copy_array(value)
    return copied


def _restore_object_state(obj: Any, saved: dict[str, Any]) -> None:
    """Restore slotted/dataclass object state while preserving mutable aliases."""
    fixed = (
        frozenset(_dataclass_state_fields(type(obj)))
        if is_dataclass(obj)
        else frozenset()
    )
    dynamic = getattr(obj, "__dict__", None)
    if dynamic is not None:
        for key in tuple(dynamic):
            if key not in fixed and key not in saved:
                del dynamic[key]

    for key, saved_value in saved.items():
        current = getattr(obj, key, _MISSING)
        if current is _MISSING:
            setattr(obj, key, _copy_array(saved_value))
            continue
        restored = _restore_array(current, saved_value)
        if restored is not current:
            setattr(obj, key, restored)


def _restore_state_dict(target: dict[str, Any], saved: dict[str, Any]) -> None:
    """Restore a state dictionary in place while preserving mutable aliases.

    The previous restore path copied the complete saved dictionary again and
    then replaced the target dictionary.  Besides repeating the snapshot cost,
    that invalidated aliases to nested arrays/lists.  This routine removes
    fields created after capture, restores existing containers in place where
    possible, and copies only replacement values.
    """
    if target.keys() != saved.keys():
        for key in tuple(target):
            if key not in saved:
                del target[key]

    for key, saved_value in saved.items():
        saved_type = type(saved_value)
        if saved_type in _IMMUTABLE_SCALAR_TYPES or isinstance(saved_value, Enum):
            target[key] = saved_value
            continue

        current = target.get(key, _MISSING)
        if current is _MISSING:
            target[key] = _copy_array(saved_value)
        elif isinstance(saved_value, np.ndarray):
            if (
                isinstance(current, np.ndarray)
                and current.shape == saved_value.shape
            ):
                current[...] = saved_value
            else:
                target[key] = saved_value.copy()
        elif saved_type is list:
            if type(current) is list:
                if not saved_value or all(
                    _is_immutable_scalar(item) for item in saved_value
                ):
                    current[:] = saved_value
                else:
                    current[:] = [_copy_array(item) for item in saved_value]
            else:
                target[key] = _copy_list(saved_value)
        elif saved_type is dict and type(current) is dict:
            _restore_state_dict(current, saved_value)
        elif saved_type is set and type(current) is set:
            current.clear()
            current.update(_copy_array(item) for item in saved_value)
        else:
            target[key] = _copy_array(saved_value)

def _iter_springs(
    model: Any,
    *,
    quads: Iterable[Any] | None = None,
    interfaces: Iterable[Any] | None = None,
) -> Iterable[Any]:
    seen: set[int] = set()
    quad_values = model.collections.quads.values() if quads is None else quads
    interface_values = (
        model.collections.interfaces.values() if interfaces is None else interfaces
    )
    for quad in quad_values:
        spring = getattr(quad, "spring", None)
        if (
            spring is not None
            and not getattr(spring, "_histra_batch_managed", False)
            and id(spring) not in seen
        ):
            seen.add(id(spring))
            yield spring
    for intf in interface_values:
        for name in ("trasv_1", "trasv_2", "slid", "slid_out_plan"):
            for spring in getattr(intf, name, ()):
                if (
                    spring is not None
                    and not getattr(spring, "_histra_batch_managed", False)
                    and id(spring) not in seen
                ):
                    seen.add(id(spring))
                    yield spring


@dataclass
class SolverStateSnapshot:
    """Captured global, integrator, element, and constitutive state."""

    p: Any
    ls: Any
    integrator: Any
    convergence_test: Any
    line_search: Any
    program_state: dict[str, Any]
    linear_state: dict[str, Any]
    manager_state: dict[str, Any]
    integrator_state: dict[str, Any]
    integrator_member_state: dict[str, Any]
    convergence_state: dict[str, Any] | None
    line_search_state: dict[str, Any] | None
    quad_state: list[tuple[Any, dict[str, Any]]]
    interface_state: list[tuple[Any, dict[str, Any]]]
    spring_state: list[tuple[Any, dict[str, Any]]]
    batch_state: tuple[np.ndarray, ...] | None

    @classmethod
    def capture(
        cls,
        model: Any,
        p: Any,
        ls: Any,
        integrator: Any,
        convergence_test: Any | None = None,
        line_search: Any | None = None,
        *,
        reuse_batch_state: tuple[np.ndarray, ...] | None = None,
    ) -> "SolverStateSnapshot":
        program_state = {
            key: _copy_array(getattr(p, key))
            for key in (
                "u", "v", "max_u", "elem_max_u_key", "elem_max_u_type",
                "to_stop", "index_fact_k", "current_load_factor",
            )
        }
        linear_state = {
            "k": ls.k.copy(), "m": ls.m.copy(), "c": ls.c.copy(),
            "x": ls.x.copy(), "b": ls.b.copy(), "b0": ls.b0.copy(),
        }
        manager_state = {
            key: _copy_array(getattr(ModelManager, key))
            for key in ("_ptarget", "_fext", "_pq", "_pq_prev", "_u_total")
        }
        member_state: dict[str, Any] = {}
        for key, value in integrator.__dict__.items():
            if key in {"state", "u", "v", "u_committed"}:
                continue
            member_state[key] = _copy_array(value)
        state_data = {
            key: _copy_array(value)
            for key, value in integrator.state.__dict__.items()
            if key not in {"analysis"}
        }
        state_data["__u"] = _copy_array(integrator.u)
        state_data["__v"] = _copy_array(integrator.v)
        state_data["__u_committed"] = _copy_array(integrator.u_committed)

        runtime = ModelManager.hysteretic_batch_for(model)
        quad_values = (
            runtime.unmanaged_quads
            if runtime is not None
            else tuple(model.collections.quads.values())
        )
        interface_values = (
            runtime.unmanaged_interfaces
            if runtime is not None
            else tuple(model.collections.interfaces.values())
        )

        # Managed elements keep their complete reversible state in the dense
        # batch snapshot and do not mutate object status dictionaries during a
        # Newton trial. Avoid recursively copying their large immutable
        # geometry/stiffness containers at every public step.
        quads = []
        for quad in quad_values:
            quads.append((quad, {
                "status": _copy_state_dict(quad.status.__dict__),
                "sigma_initial": float(getattr(quad, "sigma_initial", 0.0)),
            }))
        interfaces = []
        for intf in interface_values:
            interfaces.append((intf, {
                "status": _copy_state_dict(intf.status.__dict__),
                "f": _copy_array(intf.f),
            }))
        if runtime is not None:
            sliding_interfaces = (
                tuple(
                    runtime.records[int(idx)].interface
                    for idx in runtime._unmanaged_sliding_record_indices
                )
                if runtime._unmanaged_sliding_record_indices.size
                else ()
            )
            quad_spring_sources = runtime.unmanaged_quads
            interface_spring_sources = (*runtime.unmanaged_interfaces, *sliding_interfaces)
        else:
            quad_spring_sources = model.collections.quads.values()
            interface_spring_sources = model.collections.interfaces.values()

        springs = [
            (spring, _copy_object_state(spring))
            for spring in _iter_springs(
                model,
                quads=quad_spring_sources,
                interfaces=interface_spring_sources,
            )
        ]
        batch_state = None
        if runtime is not None:
            # Only disposable iteration snapshots may consume prior buffers;
            # independent step/line-search snapshots use fresh storage.
            batch_state = (
                runtime.snapshot() if reuse_batch_state is None
                else runtime.snapshot(reuse=reuse_batch_state)
            )
        return cls(
            p=p,
            ls=ls,
            integrator=integrator,
            convergence_test=convergence_test,
            line_search=line_search,
            program_state=program_state,
            linear_state=linear_state,
            manager_state=manager_state,
            integrator_state=state_data,
            integrator_member_state=member_state,
            convergence_state=_copy_state_dict(convergence_test.__dict__) if convergence_test else None,
            line_search_state=_copy_state_dict(line_search.__dict__) if line_search else None,
            quad_state=quads,
            interface_state=interfaces,
            spring_state=springs,
            batch_state=batch_state,
        )

    def restore(self) -> None:
        for key, saved in self.program_state.items():
            current = getattr(self.p, key)
            setattr(self.p, key, _restore_array(current, saved))
        self.ls.k = self.linear_state["k"].copy()
        self.ls.m = self.linear_state["m"].copy()
        self.ls.c = self.linear_state["c"].copy()
        self.ls.x[...] = self.linear_state["x"]
        self.ls.b[...] = self.linear_state["b"]
        self.ls.b0[...] = self.linear_state["b0"]

        for key, saved in self.manager_state.items():
            current = getattr(ModelManager, key)
            setattr(ModelManager, key, _restore_array(current, saved))

        reserved_integrator = {"state", "u", "v", "u_committed"}
        for key in list(self.integrator.__dict__):
            if key not in reserved_integrator and key not in self.integrator_member_state:
                del self.integrator.__dict__[key]
        for key, saved in self.integrator_member_state.items():
            current = getattr(self.integrator, key, None)
            setattr(self.integrator, key, _restore_array(current, saved))

        saved_state_keys = {
            key for key in self.integrator_state if not key.startswith("__")
        }
        for key in list(self.integrator.state.__dict__):
            if key != "analysis" and key not in saved_state_keys:
                del self.integrator.state.__dict__[key]
        for key, saved in self.integrator_state.items():
            if key.startswith("__"):
                continue
            current = getattr(self.integrator.state, key, None)
            setattr(self.integrator.state, key, _restore_array(current, saved))
        self.integrator.u = _restore_array(self.integrator.u, self.integrator_state["__u"])
        self.integrator.v = _restore_array(self.integrator.v, self.integrator_state["__v"])
        self.integrator.u_committed = _restore_array(
            self.integrator.u_committed, self.integrator_state["__u_committed"]
        )
        # Re-establish aliases used by the static solver.
        if isinstance(self.p.u, np.ndarray) and isinstance(self.integrator.u, np.ndarray):
            if self.p.u is not self.integrator.u:
                self.integrator.u = self.p.u
        if isinstance(self.p.v, np.ndarray) and isinstance(self.integrator.v, np.ndarray):
            if self.p.v is not self.integrator.v:
                self.integrator.v = self.p.v
        ModelManager._u_total = self.p.u

        if self.convergence_test is not None and self.convergence_state is not None:
            _restore_state_dict(self.convergence_test.__dict__, self.convergence_state)
        if self.line_search is not None and self.line_search_state is not None:
            _restore_state_dict(self.line_search.__dict__, self.line_search_state)

        for quad, saved in self.quad_state:
            _restore_state_dict(quad.status.__dict__, saved["status"])
            quad.sigma_initial = saved["sigma_initial"]
        for intf, saved in self.interface_state:
            _restore_state_dict(intf.status.__dict__, saved["status"])
            intf.f[:] = saved["f"]
        for spring, saved in self.spring_state:
            _restore_object_state(spring, saved)
        if self.batch_state is not None:
            runtime = ModelManager.hysteretic_batch_for(self.integrator.state.model) if hasattr(self.integrator.state, "model") else None
            if runtime is None:
                runtime = ModelManager._hysteretic_batch
            if runtime is None:
                raise RuntimeError("Cannot restore compiled hysteretic snapshot: runtime is absent")
            runtime.restore(self.batch_state)

    def fingerprint(self) -> str:
        """Stable value fingerprint used by rollback regression tests."""
        payload = (
            self.program_state,
            self.linear_state,
            self.manager_state,
            self.integrator_state,
            self.integrator_member_state,
            self.convergence_state,
            self.line_search_state,
            [saved for _obj, saved in self.quad_state],
            [saved for _obj, saved in self.interface_state],
            [saved for _obj, saved in self.spring_state],
            self.batch_state,
        )
        return hashlib.sha256(pickle.dumps(payload, protocol=5)).hexdigest()
