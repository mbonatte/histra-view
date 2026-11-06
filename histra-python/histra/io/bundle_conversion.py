"""Convert existing native exports to one verified bundle without solving again."""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path

import numpy as np

from histra.io.bundle import HistraBundleWriter


def _signature(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _discover_cases(directory):
    cases = {}
    for summary in sorted(directory.glob("*.summary.json")):
        case_id = summary.name.removesuffix(".summary.json")
        data = json.loads(summary.read_text(encoding="utf-8"))
        files = data.get("files", {})
        declared = files.get("fields")
        fields = directory / declared if declared else None
        if fields is not None and not fields.is_file():
            raise FileNotFoundError(fields)
        if "fields" not in files:
            fields = next((p for p in (directory / f"{case_id}.fields.npz", directory / f"{case_id}.fields.h5") if p.is_file()), None)
        cases[case_id] = (summary, fields)
    for pattern, suffix in (("*.fields.npz", ".fields.npz"), ("*.fields.h5", ".fields.h5")):
        for fields in sorted(directory.glob(pattern)):
            case_id = fields.name.removesuffix(suffix)
            cases.setdefault(case_id, (None, fields))
    if not cases:
        raise ValueError(f"No native results found in {directory}")
    return cases


class _PortableArrays(Mapping):
    """h5py variable-length scalar strings become explicit Unicode, never pickle."""
    def __init__(self, results):
        self.results = results

    def __iter__(self):
        return iter(self.results.keys())

    def __len__(self):
        return len(self.results.keys())

    def __getitem__(self, key):
        value = np.asarray(self.results[key])
        if value.dtype.hasobject and value.shape == ():
            scalar = value.item()
            if isinstance(scalar, bytes):
                return np.asarray(scalar.decode("utf-8"))
            if isinstance(scalar, str):
                return np.asarray(scalar)
        return value


def _find_model(directory, summary):
    name = Path(summary.get("metadata", {}).get("model_file", "")).name
    if not name or Path(name).suffix.lower() != ".hrx":
        return None
    candidates = (directory / name, directory.parent / name,
                  directory.parent / "models" / name, directory.parent.parent / "models" / name)
    return next((path for path in candidates if path.is_file()), None)


def _pack_case(writer, directory, case_id, paths, explicit_model):
    from histra.io.results_reader import SimulationResults

    summary_path, fields_path = paths
    with SimulationResults.load(summary_path or fields_path) as result:
        source = explicit_model or _find_model(directory, result.summary)
        model_sha = writer.add_model(source) if source else None
        # Respect explicit curve-only manifests even if stale sibling arrays exist.
        arrays = _PortableArrays(result) if fields_path is not None else {}
        writer.add_case(case_id, result.summary or None, arrays, model_sha256=model_sha)


def _check_unchanged(signatures):
    for path, expected in signatures.items():
        if not path.is_file() or _signature(path) != expected:
            raise RuntimeError(f"Result source changed during packing: {path}")


def pack_results_directory(
    directory: str | Path,
    filepath: str | Path,
    *,
    model_path: str | Path | None = None,
    attachments=(),
    metadata=None,
    overwrite: bool = False,
    remove_source: bool = False,
) -> Path:
    """Pack a fixed snapshot of native exports; optionally remove verified case files.

    Source HRX files and explicit attachments are retained. A running producer
    should finish before remove_source is used. New cases created after discovery
    are outside the snapshot and are never deleted.
    """
    directory, filepath = Path(directory).resolve(), Path(filepath).resolve()
    cases = _discover_cases(directory)
    sources = {path for pair in cases.values() for path in pair if path is not None}
    if remove_source and any(not path.resolve().is_relative_to(directory) for path in sources):
        raise ValueError("Source cleanup is restricted to the input directory")
    explicit_model = Path(model_path).resolve() if model_path is not None else None
    manifests = sorted(directory.glob("*.session.json"))
    supplied = list(dict.fromkeys(Path(path).resolve() for path in (*attachments, *manifests)))
    signatures = {path: _signature(path) for path in sources | set(supplied)}
    if any(Path(path).resolve() == filepath for path in supplied):
        raise ValueError("A bundle cannot be its own attachment")
    obsolete = _obsolete_manifests(manifests, sources) if remove_source else []
    bundle_meta = dict(metadata or {})
    bundle_meta["source_case_count"] = len(cases)
    with HistraBundleWriter(filepath, metadata=bundle_meta, overwrite=overwrite) as writer:
        for case_id, paths in cases.items():
            _pack_case(writer, directory, case_id, paths, explicit_model)
        for attachment in supplied:
            writer.add_attachment(attachment)
        _check_unchanged(signatures)
    # Publication already verified every unique payload against its original hash.
    if remove_source:
        _check_unchanged(signatures)
        for source in sorted(sources):
            source.unlink()
        for manifest in obsolete:
            manifest.unlink()
    return filepath


def _obsolete_manifests(manifests, removed_sources):
    obsolete = []
    removed = {path.name for path in removed_sources}
    for path in manifests:
        data = json.loads(path.read_text(encoding="utf-8"))
        references = [Path(case[key]).name for case in data.get("cases", [])
                      for key in ("summary", "fields") if case.get(key)]
        if references and all(name in removed for name in references):
            obsolete.append(path)
    return obsolete
