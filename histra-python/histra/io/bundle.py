"""Atomic single-file results bundles: ZIP/LZMA, shared arrays, no extraction."""
from __future__ import annotations

from collections.abc import Mapping
import copy
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import tempfile
import time
import zipfile

import numpy as np

from histra.io.bundle_codec import (
    ARRAY_ENCODING, BUNDLE_FORMAT, BUNDLE_VERSION,
    array_descriptor, encode_array, decode_array, validate_descriptor,
)


def _json_bytes(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _generator():
    try:
        return f"histra-python {version('histra-python')}"
    except PackageNotFoundError:
        return "histra-python source"


class HistraBundleWriter:
    """Write in a sibling temporary file; publish only after complete verification."""

    def __init__(self, filepath, *, metadata=None, overwrite=True):
        self._overwrite = overwrite
        self.path = Path(filepath)
        if self.path.suffix.lower() != ".histra":
            raise ValueError("Bundle filename must end in .histra")
        if self.path.exists() and not overwrite:
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        os.close(fd)
        self._temporary = Path(temporary)
        self._zip = zipfile.ZipFile(self._temporary, "w", compression=zipfile.ZIP_LZMA, allowZip64=True)
        self.manifest = {
            "format": BUNDLE_FORMAT, "schema_version": BUNDLE_VERSION,
            "array_encoding": ARRAY_ENCODING, "compression": "ZIP_LZMA",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "generator": _generator(), "metadata": dict(metadata or {}),
            "cases": {}, "objects": {}, "models": {}, "attachments": {},
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self._zip.writestr("manifest.json", _json_bytes(self.manifest))
            self._zip.close()
            if exc_type is None:
                verify_bundle(self._temporary)
                if self._overwrite:
                    os.replace(self._temporary, self.path)
                else:
                    os.link(self._temporary, self.path)
        finally:
            self._zip.close()
            self._temporary.unlink(missing_ok=True)

    def add_model(self, path):
        path = Path(path)
        return self._add_blob("models", path.name, path.read_bytes(), ".hrx")

    def add_attachment(self, path, *, name=None):
        path = Path(path)
        key = name or path.name
        if key in self.manifest["attachments"]:
            raise ValueError(f"Duplicate attachment: {key}")
        return self._add_blob("attachments", key, path.read_bytes(), path.suffix)

    def _add_blob(self, group, name, payload, suffix):
        digest = hashlib.sha256(payload).hexdigest()
        member = f"{group}/{digest}{suffix}"
        records = self.manifest[group]
        key = digest if group == "models" else name
        if key not in records:
            if member not in self._zip.namelist():
                self._zip.writestr(member, payload)
            records[key] = {"filename": name, "member": member, "sha256": digest, "nbytes": len(payload)}
        return digest

    def add_case(self, case_id, summary, arrays, *, model_sha256=None):
        if not isinstance(case_id, str) or not case_id or case_id in self.manifest["cases"]:
            raise ValueError(f"Invalid or duplicate bundle case: {case_id!r}")
        summary = copy.deepcopy(summary) if summary is not None else None
        expected = (summary or {}).get("metadata", {}).get("model_sha256")
        if model_sha256 and expected and model_sha256 != expected:
            raise ValueError(f"Model SHA-256 mismatch for case {case_id}")
        references = {key: self._add_array(arrays[key]) for key in arrays}
        if summary is not None:
            summary["files"] = {"bundle": self.path.name, "case_id": case_id}
            summary["curve_only"] = not bool(references)
        self.manifest["cases"][case_id] = {
            "summary": summary, "arrays": references,
            "model_sha256": model_sha256 or expected, "curve_only": not bool(references),
        }

    def _add_array(self, value):
        digest, descriptor, raw = array_descriptor(value)
        if digest not in self.manifest["objects"]:
            self._zip.writestr(f"objects/{digest}.bin", encode_array(raw, np.dtype(descriptor["dtype"]).itemsize))
            self.manifest["objects"][digest] = descriptor
        return digest


class BundleStore:
    """One shared ZIP handle and manifest; numerical arrays remain lazy."""

    def __init__(self, path):
        self.path = Path(path)
        self._zip = zipfile.ZipFile(path, "r")
        self._references = 0
        try:
            names = self._zip.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate ZIP members in .histra bundle")
            self.manifest = json.loads(self._zip.read("manifest.json"))
            self._validate_manifest()
        except Exception:
            self._zip.close()
            raise

    def _validate_manifest(self):
        manifest = self.manifest
        if not isinstance(manifest, dict):
            raise ValueError("Invalid bundle manifest")
        if manifest.get("format") != BUNDLE_FORMAT or manifest.get("schema_version") != BUNDLE_VERSION:
            raise ValueError("Unsupported .histra bundle format or schema version")
        if manifest.get("array_encoding") != ARRAY_ENCODING or manifest.get("compression") != "ZIP_LZMA":
            raise ValueError("Unsupported .histra array encoding or compression")
        for group in ("cases", "objects", "models", "attachments"):
            if not isinstance(manifest.get(group), dict):
                raise ValueError(f"Invalid bundle {group}")
        for digest, descriptor in manifest["objects"].items():
            if not _is_digest(digest):
                raise ValueError("Invalid bundle object identifier")
            _, _, size = validate_descriptor(descriptor)
            self._check_member(f"objects/{digest}.bin", size)
        if not isinstance(manifest.get("metadata"), dict):
            raise ValueError("Invalid bundle metadata")
        self._validate_cases()
        self._validate_blobs()

    def _validate_cases(self):
        objects = self.manifest["objects"]
        for case_id, case in self.manifest["cases"].items():
            if not isinstance(case_id, str) or not case_id or not isinstance(case, dict):
                raise ValueError("Invalid bundle case")
            summary = case.get("summary")
            if summary is not None:
                _validate_summary(summary)
            arrays = case.get("arrays")
            if not isinstance(arrays, dict) or any(not isinstance(k, str) or not isinstance(v, str) or v not in objects for k, v in arrays.items()):
                raise ValueError("Bundle case refers to missing arrays")

    def _validate_blobs(self):
        for group in ("models", "attachments"):
            for blob in self.manifest[group].values():
                if not isinstance(blob, dict) or not _is_digest(blob.get("sha256")):
                    raise ValueError("Invalid bundle blob")
                if not isinstance(blob.get("member"), str) or type(blob.get("nbytes")) is not int or blob["nbytes"] < 0:
                    raise ValueError("Invalid bundle blob descriptor")
                self._check_member(blob["member"], blob["nbytes"])

    def _check_member(self, name, size):
        try:
            member = self._zip.getinfo(name)
        except KeyError as exc:
            raise ValueError(f"Missing bundle member: {name}") from exc
        if member.file_size != size:
            raise ValueError(f"Bundle member length mismatch: {name}")

    def array(self, digest):
        descriptor = self.manifest["objects"][digest]
        return decode_array(self._zip.read(f"objects/{digest}.bin"), descriptor, digest)

    def blob(self, group, key):
        descriptor = self.manifest[group][key]
        payload = self._zip.read(descriptor["member"])
        if hashlib.sha256(payload).hexdigest() != descriptor["sha256"]:
            raise ValueError(f"Bundle {group} checksum mismatch")
        return payload

    def case_data(self, case_id=None):
        cases = self.manifest["cases"]
        if case_id is None:
            if len(cases) != 1:
                raise ValueError("Select a .histra case with case_id=... or use load_session()")
            case_id = next(iter(cases))
        if case_id not in cases:
            raise KeyError(f"Unknown .histra case: {case_id}")
        self._references += 1
        return BundleCaseData(self, case_id)

    def close(self):
        self._zip.close()


class BundleCaseData(Mapping):
    def __init__(self, store, case_id):
        self.store = store
        self.case_id = case_id
        self.case = store.manifest["cases"][case_id]
        self._closed = False

    def __getitem__(self, key):
        if self._closed:
            raise ValueError("Bundle case is closed")
        return self.store.array(self.case["arrays"][key])

    def __contains__(self, key):
        return not self._closed and key in self.case["arrays"]

    def __iter__(self):
        return iter(self.case["arrays"])

    def __len__(self):
        return len(self.case["arrays"])

    def close(self):
        if not self._closed:
            self._closed = True
            self.store._references -= 1
            if self.store._references == 0:
                self.store.close()


def _validate_summary(summary):
    if not isinstance(summary, dict) or not isinstance(summary.get("metadata", {}), dict):
        raise ValueError("Invalid bundle summary")
    version = str(summary.get("metadata", {}).get("schema_version", "1.0.0"))
    if version.split(".")[0] not in {"1", "2"}:
        raise ValueError(f"Unsupported simulation result schema: {version}")


def _is_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def verify_bundle(path):
    """Read and checksum every unique array and embedded source/attachment."""
    store = BundleStore(path)
    try:
        for digest in store.manifest["objects"]:
            store.array(digest)
        for group in ("models", "attachments"):
            for key in store.manifest[group]:
                store.blob(group, key)
    finally:
        store.close()
