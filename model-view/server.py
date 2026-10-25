"""Local model view service. Run: python3 model-view/server.py"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import gzip
import argparse
import hashlib
import json
import mimetypes
import subprocess
import threading
from urllib.parse import urlsplit, parse_qs
import xml.etree.ElementTree as ET

from hrx_model import parse_hrx

BASE = Path(__file__).resolve().parent
MAX_UPLOAD = 32 * 1024 * 1024
MAX_RESULT_UPLOAD = 1024 * 1024 * 1024
RESULT_SOURCES = {
    "bridge": {"label": "3D Bridge", "folder": "3D_bridge", "model": "Bridge.hrx", "output": "pdelta_soft_subgrade_phase4_results.json"},
    "wall": {"label": "Wall model", "folder": "wall_model", "model": "overturning_wall_elastic_foundation.hrx", "output": "overturning_wall_raw_output.json"},
}
RESULT_LOCK = threading.Lock()
RESULT_CACHE = {}
INTERFACE_CACHE = {}
CONTOUR_CACHE = {}


def result_catalog():
    sources = [{"id": key, "label": source["label"]} for key, source in RESULT_SOURCES.items()
               if (BASE.parent / source["folder"] / source["output"]).is_file()]
    return {"sources": sources, "defaultSource": "bridge" if any(s["id"] == "bridge" for s in sources) else "wall"}


def saved_results(source_id, mode="", analysis="", key=""):
    source = RESULT_SOURCES.get(source_id)
    if source is None:
        raise ValueError("Unknown saved result source.")
    if mode and (not analysis or len(analysis) > 200):
        raise ValueError("Choose a saved analysis stage.")
    if mode == "interface" and (not key.isdecimal() or len(key) > 10 or int(key) < 1):
        raise ValueError("Choose a valid interface ID.")
    files = tuple(BASE.parent / source["folder"] / source[k] for k in ("model", "output"))
    with RESULT_LOCK:
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None for p in (*files, BASE / "result_preview.py", BASE / "bridge_v2.py"))
        if source_id == "bridge":
            try:
                from bridge_v2 import cache_stamp
                stamp += cache_stamp(files[1])
            except (OSError, ValueError):
                pass
        cache = INTERFACE_CACHE if mode == "interface" else CONTOUR_CACHE if mode == "contours" else RESULT_CACHE
        cache_key = source_id, stamp, analysis, key
        if cache_key not in cache:
            from result_preview import project_results, project_contours, project_interface
            if mode == "interface":
                payload = project_interface(str(files[1]), analysis, int(key))
            elif mode == "contours":
                payload = project_contours(str(files[1]), analysis)
            else:
                payload = project_results(str(files[0]), str(files[1]), analysis)
            payload["sourceId"] = source_id
            if len(cache) >= (200 if mode == "interface" else 4):
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
            if source_id not in RESULT_SOURCES or mode not in ("", "contours", "interface"):
                return self.reply(404, {"error": "Unknown saved result source or endpoint."})
            try:
                query = parse_qs(urlsplit(self.path).query)
                return self.reply(200, saved_results(source_id, mode, query.get("analysis", [""])[0], query.get("key", [""])[0]))
            except (ValueError, KeyError, IndexError, OSError, subprocess.TimeoutExpired) as exc:
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

    def results_import(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_RESULT_UPLOAD:
                return self.reply(413, {"error": "Upload file between 1 byte and 1 GiB."})
            data = self.rfile.read(length)
            from result_preview import project_results
            raw = json.loads(data)
            if "schemaVersion" in raw and "analyses" in raw:
                return self.reply(200, raw)
            import tempfile
            hrx_candidate = BASE.parent / "3D_bridge/Bridge.hrx"
            hrx_path = str(hrx_candidate) if hrx_candidate.is_file() else None
            with tempfile.NamedTemporaryFile("wb+", suffix=".json", delete=True) as tmp:
                tmp.write(data)
                tmp.flush()
                result = project_results(hrx_path, tmp.name)
            for sid, src in RESULT_SOURCES.items():
                model_file = BASE.parent / src["folder"] / src["model"]
                if model_file.is_file() and hashlib.sha256(model_file.read_bytes()).hexdigest().lower() == result.get("modelSha256", "").lower():
                    result["sourceId"] = sid
                    break
            return self.reply(200, result)
        except Exception as exc:
            return self.reply(400, {"error": f"Import failed: {exc}"})

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
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.model_path = args.model
    print(f"HiStrA model viewer: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
