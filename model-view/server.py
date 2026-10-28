"""Local model view service. Run: python3 model-view/server.py"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import gzip
import argparse
import hashlib
import json
import mimetypes
import sqlite3
import subprocess
import tempfile
import threading
import shutil
import re
from urllib.parse import urlsplit, parse_qs
import xml.etree.ElementTree as ET

from hrx_model import parse_hrx

BASE = Path(__file__).resolve().parent
MAX_UPLOAD = 32 * 1024 * 1024
MAX_RESULT_UPLOAD = 8 * 1024 * 1024 * 1024
IMPORT_ROOT = Path(tempfile.gettempdir()) / "histra-view-imports"
IMPORT_ROOT.mkdir(parents=True, exist_ok=True)
IMPORT_SESSIONS = {}
IMPORT_LOCK = threading.Lock()
RESULT_SOURCES = {}



def _source_path(folder: str, *parts: str) -> Path:
    """Resolve a source both in the old flat layout and under results/."""
    root = BASE.parent
    flat = root / folder
    if flat.exists():
        return flat.joinpath(*parts)
    return (root / "results" / folder).joinpath(*parts)
RESULT_LOCK = threading.Lock()
RESULT_CACHE = {}
INTERFACE_CACHE = {}
CONTOUR_CACHE = {}
FIELD_CACHE = {}
MODAL_CACHE = {}


def _source_available(source_id, source):
    output = _source_path(source["folder"], source["output"])
    if not output.is_file():
        return False
    if source_id not in ("bridge", "bridge2d"):
        return True
    try:
        raw = json.loads(output.read_text())
        referenced = []
        for entry in raw.get("files", {}).values():
            if isinstance(entry, dict):
                referenced.extend(value for value in entry.values() if value)
        baseline = raw.get("baseline_case", {})
        if isinstance(baseline, dict):
            referenced.extend(baseline[key] for key in ("summary", "fields")
                              if isinstance(baseline.get(key), str))
        return all((output.parent / reference).is_file() for reference in referenced)
    except (ValueError, OSError):
        return False


def result_catalog():
    sources = [{"id": key, "label": source["label"]} for key, source in RESULT_SOURCES.items()
               if _source_available(key, source)]
    preferred = ("native_soil", "bridge")
    default = next((key for key in preferred if any(s["id"] == key for s in sources)),
                   sources[0]["id"] if sources else None)
    return {"sources": sources, "defaultSource": default}


def saved_results(source_id, mode="", analysis="", key="", step=None):
    source = RESULT_SOURCES.get(source_id)
    if source is None:
        raise ValueError("Unknown saved result source.")
    if mode and (not analysis or len(analysis) > 200):
        raise ValueError("Choose a saved analysis stage.")
    if mode == "interface" and (not key.isdecimal() or len(key) > 10 or int(key) < 1):
        raise ValueError("Choose a valid interface ID.")
    native_csharp = source.get("adapter") == "csharp"
    native_histra = source.get("adapter") == "histra"
    if mode == "fields" and not (native_csharp or native_histra):
        raise ValueError("Per-step stress fields are not available for this source.")
    if mode == "fields" and step is None:
        raise ValueError("Choose a saved step.")
    if mode == "modal" and not native_histra:
        raise ValueError("Modal attachments are available only for .histra sources.")
    files = tuple(_source_path(source["folder"], source[k]) for k in ("model", "output"))
    with RESULT_LOCK:
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None for p in (*files, BASE / "result_preview.py", BASE / "bridge_v2.py", BASE / "csharp_results.py", BASE / "histra_results.py", BASE / "result_fields.py"))
        if source_id in ("bridge", "bridge2d"):
            try:
                from bridge_v2 import cache_stamp
                stamp += cache_stamp(files[1])
            except (OSError, ValueError):
                pass
        cache = (INTERFACE_CACHE if mode == "interface" else
                 CONTOUR_CACHE if mode == "contours" else
                 FIELD_CACHE if mode == "fields" else
                 MODAL_CACHE if mode == "modal" else
                 RESULT_CACHE)
        cache_key = source_id, stamp, analysis, key, step
        if cache_key not in cache:
            from result_preview import project_results, project_contours, project_interface
            if mode == "modal":
                from histra_results import project_histra_modal
                payload = project_histra_modal(str(files[1]), analysis)
            elif mode == "interface":
                if native_csharp:
                    from csharp_results import project_interface_csharp
                    payload = project_interface_csharp(str(files[0]), str(files[1]), analysis, int(key), step)
                elif native_histra:
                    from histra_results import project_interface_histra
                    payload = project_interface_histra(str(files[1]), analysis, int(key))
                else:
                    payload = project_interface(str(files[1]), analysis, int(key))
            elif mode == "contours":
                if native_csharp:
                    from csharp_results import project_contours_csharp
                    payload = project_contours_csharp(str(files[0]), str(files[1]), analysis, step)
                elif native_histra:
                    from histra_results import project_contours_histra
                    payload = project_contours_histra(str(files[1]), analysis)
                else:
                    payload = project_contours(str(files[1]), analysis)
            elif mode == "fields":
                if native_histra:
                    from histra_results import project_histra_fields
                    payload = project_histra_fields(str(files[1]), analysis, int(step))
                else:
                    from csharp_results import project_csharp_fields
                    payload = project_csharp_fields(str(files[0]), str(files[1]), analysis, int(step))
            elif source.get("lazy_fields"):
                from csharp_results import project_csharp
                payload = project_csharp(
                    str(files[0]), str(files[1]), analysis,
                    include_stress_fields=False,
                )
            elif native_histra:
                from histra_results import project_histra
                payload = project_histra(
                    str(files[1]), analysis,
                    include_stress_fields=False,
                    include_modal_shapes=False,
                )
            else:
                payload = project_results(str(files[0]), str(files[1]), analysis)
            payload["sourceId"] = source_id
            payload["nativeCsharp"] = native_csharp
            # Keep every static analysis of the large native C# datasets hot.
            # A first projection is expensive; re-projecting an evicted
            # analysis is much worse than retaining the compact JSON payload.
            limit = 200 if mode == "interface" else 100 if mode == "fields" else 16
            if len(cache) >= limit:
                cache.pop(next(iter(cache)))
            cache[cache_key] = payload
        return cache[cache_key]


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, mime="application/json"):
        if mime == "application/json" and not isinstance(body, bytes):
            data = json.dumps(body, allow_nan=False, separators=(",", ":")).encode()
        else:
            data = body
        compressed = mime == "application/json" and len(data) > 65536 and "gzip" in self.headers.get("Accept-Encoding", "")
        if compressed: data = gzip.compress(data, compresslevel=1)
        self.send_response(status)
        if compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/results/catalog":
            return self.reply(200, result_catalog())
        parts = route.strip("/").split("/")
        if len(parts) in (3, 4) and parts[:2] == ["api", "results"]:
            source_id = parts[2]
            mode = parts[3] if len(parts) == 4 else ""
            if source_id not in RESULT_SOURCES or mode not in ("", "contours", "interface", "fields", "modal"):
                return self.reply(404, {"error": "Unknown saved result source or endpoint."})
            try:
                query = parse_qs(urlsplit(self.path).query)
                raw_step = query.get("step", [None])[0]
                step = int(raw_step) if raw_step is not None and raw_step.isdecimal() else None
                return self.reply(200, saved_results(
                    source_id, mode, query.get("analysis", [""])[0],
                    query.get("key", [""])[0], step,
                ))
            except (ValueError, KeyError, IndexError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
                return self.reply(400 if mode else 503, {"error": str(exc)})
        if route == "/api/model/example":
            return self.reply(200, parse_hrx(self.server.model_path.read_bytes(), self.server.model_path.name))
        if route == "/api/health":
            return self.reply(200, {"status": "ok"})
        assets = {"/": BASE / "static/index.html"}
        assets.update({f"/static/{p.name}": p for p in (BASE / "static").iterdir() if p.is_file()})
        assets.update({"/vendor/three.module.js": BASE / "node_modules/three/build/three.module.js",
                       "/vendor/three.core.js": BASE / "node_modules/three/build/three.core.js",
                       "/vendor/OrbitControls.js": BASE / "node_modules/three/examples/jsm/controls/OrbitControls.js"})
        path = assets.get(route)
        if path is None or not path.is_file():
            return self.reply(404, {"error": "Not found"})
        return self.reply(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")

    def do_POST(self):
        if urlsplit(self.path).path == "/api/material/preview":
            return self.material_preview()
        if urlsplit(self.path).path == "/api/results/import":
            return self.results_import()
        if urlsplit(self.path).path == "/api/results/import/complete":
            return self.import_complete()
        if urlsplit(self.path).path != "/api/model":
            return self.reply(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_UPLOAD:
                return self.reply(413, {"error": "Choose an HRX file between 1 byte and 32 MiB."})
            data = self.rfile.read(length)
            model = parse_hrx(data, "Imported model.hrx")
        except (ValueError, UnicodeError, ET.ParseError) as exc:
            return self.reply(400, {"error": str(exc)})
        return self.reply(200, model)

    def _extract_import_archive(self, archive_path):
        """Extract a local RAR/ZIP upload and return its HRX/result pair."""
        try:
            import libarchive
        except ImportError as exc:
            raise ValueError("Archive import requires libarchive-c; install model-view/requirements-preview.txt.") from exc
        target_dir = Path(tempfile.mkdtemp(prefix="extract-", dir=IMPORT_ROOT))
        total = 0
        try:
            with libarchive.file_reader(str(archive_path)) as entries:
                for entry in entries:
                    name = Path(entry.pathname).name
                    if not name or name in (".", "..") or getattr(entry, "isdir", False):
                        continue
                    total += int(entry.size or 0)
                    if total > MAX_RESULT_UPLOAD:
                        raise ValueError("Expanded archive exceeds the 8 GiB import limit.")
                    target = target_dir / name
                    with target.open("wb") as handle:
                        for block in entry.get_blocks():
                            handle.write(block)
            files = [path for path in target_dir.iterdir() if path.is_file()]
            models = sorted(path for path in files if path.suffix.lower() in (".hrx", ".xml"))
            csharp = sorted(path for path in files if path.suffix.lower() == ".results")
            histra = sorted(path for path in files if path.suffix.lower() == ".histra")
            json_files = sorted(path for path in files if path.suffix.lower() == ".json")
            result = (csharp or histra or json_files)
            if not result:
                raise ValueError("Archive contains no .Results, .histra, or .json result file.")
            if csharp and not models:
                raise ValueError("Archive contains a native .Results database but no HRX model.")
            model = models[0] if models else None
            return model, result[0], target_dir
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise

    def _import_project(self, model_path, result_path, source_id="imported", lazy=False):
        suffix = Path(result_path).suffix.lower()
        if suffix in (".rar", ".zip"):
            model, result, extracted = self._extract_import_archive(result_path)
            try:
                return self._import_project(model, result, source_id, lazy)
            finally:
                shutil.rmtree(extracted, ignore_errors=True)
        from result_preview import project_results
        if suffix == ".histra":
            from histra_results import project_histra
            payload = project_histra(
                str(result_path),
                include_stress_fields=False,
                include_modal_shapes=False,
            )
        elif suffix == ".results":
            if model_path is None or not Path(model_path).is_file():
                raise ValueError("A native C# .Results import also needs its HRX model file.")
            from csharp_results import project_csharp
            payload = project_csharp(
                str(model_path), str(result_path),
                include_stress_fields=not lazy,
            )
        elif suffix == ".json":
            raw = json.loads(Path(result_path).read_text())
            if "schemaVersion" in raw and "analyses" in raw:
                payload = raw
            else:
                if model_path is None or not Path(model_path).is_file():
                    raise ValueError("This result JSON needs its matching HRX model file.")
                payload = project_results(str(model_path), str(result_path))
        else:
            raise ValueError(f"Unsupported result file type: {Path(result_path).suffix or Path(result_path).name}")
        payload["sourceId"] = source_id
        payload["nativeCsharp"] = bool(lazy)
        payload["imported"] = True
        payload["name"] = Path(model_path).name if model_path else Path(result_path).name
        return payload

    def _import_cleanup(self, files):
        for path in files:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def results_import(self):
        query = parse_qs(urlsplit(self.path).query)
        import_id = (query.get("import_id") or [""])[0]
        role = (query.get("role") or [""])[0]
        if import_id or role:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", import_id or ""):
                return self.reply(400, {"error": "Invalid import id."})
            if role not in ("model", "results"):
                return self.reply(400, {"error": "Import role must be model or results."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_RESULT_UPLOAD:
                    return self.reply(413, {"error": "Upload file between 1 byte and 8 GiB."})
                filename = (query.get("name") or ["upload"])[0]
                suffix = Path(filename).suffix.lower()
                allowed = {
                    "model": {".hrx", ".xml"},
                    "results": {".results", ".histra", ".json", ".rar", ".zip"},
                }[role]
                if suffix not in allowed:
                    return self.reply(400, {"error": f"Unsupported {role} file type: {suffix or filename}"})
                target = IMPORT_ROOT / f"{import_id}-{role}{suffix}"
                remaining = length
                with target.open("wb") as handle:
                    while remaining > 0:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError("Upload ended before Content-Length.")
                        handle.write(chunk)
                        remaining -= len(chunk)
                with IMPORT_LOCK:
                    IMPORT_SESSIONS.setdefault(import_id, {})[role] = {
                        "path": str(target), "name": filename,
                    }
                return self.reply(200, {"pending": True, "importId": import_id, "role": role})
            except (ValueError, OSError) as exc:
                return self.reply(400, {"error": f"Upload failed: {exc}"})

        # Backwards-compatible single JSON import. Large native files must use
        # the staged model/results upload above.
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_RESULT_UPLOAD:
                return self.reply(413, {"error": "Upload file between 1 byte and 8 GiB."})
            data = self.rfile.read(length)
            raw = json.loads(data)
            if "schemaVersion" in raw and "analyses" in raw:
                raw["sourceId"] = "imported"
                raw["nativeCsharp"] = False
                raw["imported"] = True
                return self.reply(200, raw)
            return self.reply(400, {"error": "Native result imports need an HRX model and the staged import endpoint."})
        except Exception as exc:
            return self.reply(400, {"error": f"Import failed: {exc}"})

    def import_complete(self):
        query = parse_qs(urlsplit(self.path).query)
        import_id = (query.get("import_id") or [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", import_id or ""):
            return self.reply(400, {"error": "Invalid import id."})
        with IMPORT_LOCK:
            session = IMPORT_SESSIONS.pop(import_id, None)
        if not session:
            return self.reply(404, {"error": "Import session not found. Upload the files again."})
        result_entry = session.get("results")
        model_entry = session.get("model")
        uploaded = [entry["path"] for entry in session.values() if isinstance(entry, dict)]
        source_id = f"imported_{import_id}"
        source_dir = IMPORT_ROOT / source_id
        try:
            if not result_entry:
                raise ValueError("No result file was uploaded. Select an HRX model and a .Results, .histra, .json, or archive file.")
            source_dir.mkdir(parents=True, exist_ok=True)
            result_path = Path(result_entry["path"])
            model_path = Path(model_entry["path"]) if model_entry else None
            if result_path.suffix.lower() in (".rar", ".zip"):
                extracted_model, extracted_result, extracted_dir = self._extract_import_archive(result_path)
                try:
                    if extracted_model is not None:
                        model_path = source_dir / extracted_model.name
                        shutil.move(str(extracted_model), str(model_path))
                    else:
                        model_path = None
                    result_path = source_dir / extracted_result.name
                    shutil.move(str(extracted_result), str(result_path))
                finally:
                    shutil.rmtree(extracted_dir, ignore_errors=True)
            else:
                target_model = source_dir / (model_entry["name"] if model_entry else "model.hrx")
                if model_path is not None:
                    shutil.move(str(model_path), str(target_model))
                    model_path = target_model
                target_result = source_dir / result_entry["name"]
                shutil.move(str(result_path), str(target_result))
                result_path = target_result
            suffix = result_path.suffix.lower()
            source = {
                "label": f"Imported: {result_path.name}",
                "folder": str(source_dir),
                "model": model_path.name if model_path else "",
                "output": result_path.name,
                "adapter": "csharp" if suffix == ".results" else
                           "histra" if suffix == ".histra" else "imported",
                "lazy_fields": suffix == ".results",
            }
            with IMPORT_LOCK:
                RESULT_SOURCES[source_id] = source
            payload = self._import_project(
                str(model_path) if model_path else None, str(result_path),
                source_id=source_id, lazy=suffix == ".results",
            )
            return self.reply(200, payload)
        except Exception as exc:
            with IMPORT_LOCK:
                RESULT_SOURCES.pop(source_id, None)
            shutil.rmtree(source_dir, ignore_errors=True)
            return self.reply(400, {"error": f"Import failed: {exc}"})
        finally:
            self._import_cleanup(uploaded)

    def material_preview(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 128 * 1024:
                return self.reply(413, {"error": "Material preview input is too large."})
            payload = self.rfile.read(length)
            json.loads(payload)
            python = BASE / ".venv/bin/python"
            if not python.is_file():
                return self.reply(503, {"error": "Install the material preview environment; see model-view/README.md."})
            result = subprocess.run([str(python), "-B", str(BASE / "material_preview.py")],
                                    input=payload, capture_output=True, timeout=20)
            response = json.loads(result.stdout)
            return self.reply(200 if result.returncode == 0 else 400, response)
        except subprocess.TimeoutExpired:
            return self.reply(408, {"error": "Material preview exceeded 20 seconds."})
        except (ValueError, OSError):
            return self.reply(400, {"error": "Unable to calculate preview. Check the saved material parameters and local preview dependencies."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", type=Path, default=BASE.parent / "model_example.hrx")
    args = parser.parse_args()
    # Imported datasets are session-local. Clear stale uploads from a previous
    # server process before accepting new imports.
    for child in IMPORT_ROOT.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            pass
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.model_path = args.model
    print(f"HiStrA model viewer: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
