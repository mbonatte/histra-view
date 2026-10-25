"""C#-compatible interface-material mutation between committed analyses."""
from __future__ import annotations

import copy
import warnings
from dataclasses import dataclass
from typing import Iterable, Any

from histra.preprocessing.prepare_model import rebuild_interface_springs
from histra.solver.model_manager import ModelManager
from histra.solver.restart import transfer_committed_spring_state
from histra.io.results_reader import ResultsStateError


class InterfaceMaterialMutationError(RuntimeError):
    """Raised when an interface material cannot be changed losslessly."""


class InterfaceRegistrationWarning(UserWarning):
    """A selected material-reset strategy differs from C# registration."""


class SpringHistoryResetWarning(UserWarning):
    """Explicit native compatibility discarded incompatible spring histories."""


def normalize_spring_type_change(value: str) -> str:
    policy = str(value).strip().lower()
    if policy not in {"reject", "csharp_reset"}:
        raise ValueError(
            f"Unknown spring_type_change {value!r}; expected 'reject' or 'csharp_reset'."
        )
    return policy


def normalize_interface_registration(value: str) -> str:
    strategy = str(value).strip().lower()
    if strategy not in {"csharp", "single_link"}:
        raise ValueError(
            f"Unknown interface_registration {value!r}; "
            "expected 'csharp' or 'single_link'."
        )
    return strategy


def _backup_quad_links(model: Any, keys: Iterable[int]) -> dict[int, list[list[int]]]:
    quads = getattr(model.collections, "quads", {})
    parents = set()
    for key in keys:
        interface = model.collections.interfaces[key]
        for side in (1, 2):
            if getattr(interface, f"parent_type_element{side}", None) == "Quad":
                parents.add(getattr(interface, f"parent_element_key{side}"))
    return {
        key: [list(edge) for edge in quads[key].interface_keys]
        for key in parents if key in quads
    }


def _invalidate_quad_links(quad: Any) -> None:
    quad._perf_dn_edges = None
    quad._perf_dn_areas = None


def _restore_quad_links(model: Any, backups: dict[int, list[list[int]]]) -> None:
    for key, edges in backups.items():
        quad = model.collections.quads[key]
        for target, source in zip(quad.interface_keys, edges):
            target[:] = source
        _invalidate_quad_links(quad)


def _register_material_resets(model: Any, records: Any, strategy: str) -> int:
    """Reproduce C# Set/AssignInterfaceAfference for each material reset.

    This changes neighbour multiplicity for Quad.ComputeDN; it does not clone
    interface springs or double their global force/stiffness assembly.
    """
    quads = getattr(model.collections, "quads", {})
    added = 0
    for record in records:
        interface = model.collections.interfaces[record.interface_key]
        for side in (1, 2):
            if getattr(interface, f"parent_type_element{side}", None) != "Quad":
                continue
            quad = quads[getattr(interface, f"parent_element_key{side}")]
            edge = quad.interface_keys[getattr(interface, f"face{side}")]
            if strategy == "csharp":
                edge.append(interface.key)
                added += 1
            else:
                edge[:] = list(dict.fromkeys(edge))
            _invalidate_quad_links(quad)
    return added


@dataclass(frozen=True)
class InterfaceMaterialMutationRecord:
    interface_key: int
    old_material_key: int
    new_material_key: int
    transverse_springs: int
    in_plane_springs: int
    out_of_plane_springs: int


@dataclass(frozen=True)
class InterfaceSpringHistoryReset:
    interface_key: int
    group: str
    id_local: int
    source_law: str
    target_law: str


@dataclass(frozen=True)
class InterfaceMaterialMutationReport:
    material_key: int
    records: tuple[InterfaceMaterialMutationRecord, ...]
    interface_registration: str = "csharp"
    added_quad_links: int = 0
    spring_type_change: str = "reject"
    history_resets: tuple[InterfaceSpringHistoryReset, ...] = ()
    preserve_committed_state: bool = True

    @property
    def reset_spring_count(self) -> int:
        return len(self.history_resets)

    @property
    def interface_count(self) -> int:
        return len(self.records)

    @property
    def spring_count(self) -> int:
        return sum(
            row.transverse_springs + row.in_plane_springs + row.out_of_plane_springs
            for row in self.records
        )


def _backup_interface(interface: Any) -> Any:
    """Return a rollback-safe backup without duplicating the object graph.

    ``rebuild_interface_springs`` replaces the mutable constitutive containers
    (spring lists and ``status``) instead of mutating their predecessors.  A
    shallow copy therefore keeps the exact predecessor objects needed for
    committed-state transfer and rollback while sharing immutable geometry,
    afference data and cached arrays.  Only ``f`` is copied because it is
    restored in-place on a successful mutation and must remain independent if
    a later step fails.
    """
    backup = copy.copy(interface)
    backup.f = list(interface.f)
    return backup


def _groups(interface: Any) -> tuple[list[Any], list[Any], list[Any]]:
    return interface.trasv_1, interface.slid, interface.slid_out_plan


def _transfer_groups(old: Any, new: Any, policy: str) -> list[InterfaceSpringHistoryReset]:
    old_groups = _groups(old)
    new_groups = _groups(new)
    labels = ("transverse", "in-plane", "out-of-plane")
    resets = []
    for label, source_group, target_group in zip(labels, old_groups, new_groups):
        if len(source_group) != len(target_group):
            raise InterfaceMaterialMutationError(
                f"Interface {old.key}: {label} spring count changed during material "
                f"mutation ({len(source_group)} -> {len(target_group)})."
            )
        if (
            hasattr(target_group, "copy_committed_state_from")
            and hasattr(source_group, "copy_committed_state_from")
        ):
            target_group.copy_committed_state_from(source_group)
            continue
        for index, (source, target) in enumerate(zip(source_group, target_group)):
            if type(source) is not type(target):
                if policy == "reject":
                    raise ResultsStateError(
                        "Cannot transfer committed spring state across different laws: "
                        f"{type(source).__name__} -> {type(target).__name__}. "
                        "Explicit spring_type_change='csharp_reset' discards the "
                        "incompatible history to reproduce the C# database restart."
                    )
                # Original dbOutputManager.UpdateSpringStates logs and skips
                # mismatched SpringType rows before reaching SetSpring(false).
                resets.append(InterfaceSpringHistoryReset(
                    old.key, label, index, type(source).__name__, type(target).__name__,
                ))
                continue
            transfer_committed_spring_state(source, target)
    return resets


def change_interface_materials(
    model: Any,
    interface_keys: Iterable[int],
    material_key: int,
    *,
    preserve_committed_state: bool = True,
    interface_registration: str = "csharp",
    spring_type_change: str = "reject",
) -> InterfaceMaterialMutationReport:
    """Change selected interface materials atomically.

    The C#-compatibility sequence is:

    1. rebuild each interface's spring definitions using ``material_key`` for
       both sides;
    2. restore matching spring histories onto the new definitions; changed
       classes are rejected unless selective native reset is explicit;
    3. preserve the committed Interface state and geometry/afference mapping;
    4. update compatible dense constitutive rows in place, otherwise fall
       back to the existing full compiled-runtime rebuild.

    ``interface_registration="csharp"`` appends the changed interface to its
    Quad parents as C# ReSetInterfaces/Set does. ``single_link`` retains unique
    links and emits an explicit compatibility warning. Select a strategy before
    starting the chain. The global displacement and unaffected springs are
    preserved; affected Quad normal-force caches are rebuilt.

    A changed spring class is rejected by default. Explicit
    ``spring_type_change="csharp_reset"`` retains newly constructed virgin
    springs for mismatched classes, as the guarded C# DB restart does. Matching
    classes and interface/global displacement history remain preserved. The
    report identifies each skipped spring and a warning exposes preload loss.
    """
    if model.collections is None:
        raise InterfaceMaterialMutationError("Model.collections is not initialized.")
    strategy = normalize_interface_registration(interface_registration)
    policy = normalize_spring_type_change(spring_type_change)
    material_key = int(material_key)
    if material_key != 0 and material_key not in model.collections.materials:
        raise InterfaceMaterialMutationError(
            f"Unknown interface material key {material_key}."
        )

    keys = tuple(dict.fromkeys(int(key) for key in interface_keys))
    if not keys:
        return InterfaceMaterialMutationReport(
            material_key, (), strategy, spring_type_change=policy,
            preserve_committed_state=preserve_committed_state,
        )
    missing = [key for key in keys if key not in model.collections.interfaces]
    if missing:
        raise InterfaceMaterialMutationError(
            f"Unknown interface keys: {missing}."
        )

    quad_links = _backup_quad_links(model, keys)
    runtime = ModelManager.hysteretic_batch_for(model)
    if quad_links and runtime is not None:
        # Dense committed histories must seed the full topology rebuild.
        runtime.sync_all_to_objects()
    backups = {
        key: _backup_interface(model.collections.interfaces[key]) for key in keys
    }
    # The geometry cache is immutable across a material-only rebuild.  The
    # spring factory clears these fields because it is also used during full
    # model preparation; retain them here to avoid redoing geometry work after
    # every scour step.
    geometry_caches = {
        key: (
            getattr(model.collections.interfaces[key], "_perf_di", None),
            getattr(model.collections.interfaces[key], "_perf_dj", None),
            getattr(model.collections.interfaces[key], "_perf_ecc", None),
            getattr(model.collections.interfaces[key], "_perf_area", None),
        )
        for key in keys
    }
    records: list[InterfaceMaterialMutationRecord] = []
    resets: list[InterfaceSpringHistoryReset] = []
    # Material-law construction depends only on the material and direction.
    # Share these caches across this mutation batch, exactly as full model
    # preparation does, instead of rebuilding identical law objects for every
    # interface.
    flex_law_cache: dict[Any, Any] = {}
    sliding_law_cache: dict[Any, Any] = {}
    try:
        for key in keys:
            interface = model.collections.interfaces[key]
            old = backups[key]
            # Preserve the existing SetStatus semantics exactly. InterfaceState
            # is intentionally tiny (small fixed-size vectors/matrices), so this
            # copy is negligible compared with deepcopying the whole Interface.
            old_status = copy.deepcopy(interface.status)
            old_force = list(interface.f)
            old_material_key = int(interface.material_key)

            interface.material_key = material_key
            rebuild_interface_springs(
                model,
                interface,
                flex_law_cache=flex_law_cache,
                sliding_law_cache=sliding_law_cache,
            )
            if preserve_committed_state:
                resets.extend(_transfer_groups(old, interface, policy))

            # ReSetInterfaces initializes a fresh status, then C# SetStatus
            # restores the predecessor InterfaceState.  In-memory chaining can
            # preserve that same committed state directly.
            interface.status = old_status
            interface.f[:] = old_force
            (
                interface._perf_di,
                interface._perf_dj,
                interface._perf_ecc,
                interface._perf_area,
            ) = geometry_caches[key]

            records.append(
                InterfaceMaterialMutationRecord(
                    interface_key=key,
                    old_material_key=old_material_key,
                    new_material_key=material_key,
                    transverse_springs=len(interface.trasv_1),
                    in_plane_springs=len(interface.slid),
                    out_of_plane_springs=len(interface.slid_out_plan),
                )
            )
        changed_properties = bool(records)
        if strategy == "single_link" and quad_links and changed_properties:
            warnings.warn(
                "single_link material resets retain unique Quad interface links; "
                "this differs from C# ReSetInterfaces registration and may change "
                "diagonal normal force and nonlinear response.",
                InterfaceRegistrationWarning, stacklevel=2,
            )
        added_links = _register_material_resets(model, records, strategy)
        if resets:
            warnings.warn(
                f"C# compatibility reset discarded {len(resets)} incompatible spring "
                "histories. This may remove previously carried forces/preload; "
                "matching C# output does not establish physical equilibrium. "
                "The mutation report identifies every reset spring.",
                SpringHistoryResetWarning, stacklevel=2,
            )
    except Exception:
        _restore_quad_links(model, quad_links)
        for key, backup in backups.items():
            model.collections.interfaces[key] = backup
        ModelManager.clear_hysteretic_batch()
        raise

    # Keep the large dense runtime when the replacement spring layout is
    # structurally identical.  The runtime validates *all* changed interfaces
    # before touching its arrays; any incompatibility or update error clears it
    # so the next solve follows the existing full-build path.
    changed_interfaces = tuple(model.collections.interfaces[key] for key in keys)
    if quad_links and changed_properties:
        # Its compiled edge reductions encode neighbour multiplicity.
        ModelManager.clear_hysteretic_batch()
    else:
        ModelManager.update_hysteretic_batch_material_interfaces(
            model, changed_interfaces
        )
    return InterfaceMaterialMutationReport(
        material_key, tuple(records), strategy, added_links,
        policy, tuple(resets), preserve_committed_state,
    )
