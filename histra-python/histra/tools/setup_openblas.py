"""Install Ubuntu's LP64 OpenBLAS into the active virtualenv, without sudo."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def install_openblas(destination: Path) -> Path:
    if not sys.platform.startswith("linux") or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise ValueError("This installer requires an apt-based x86_64 Linux system")
    for command in ("apt-get", "dpkg-deb"):
        if shutil.which(command) is None:
            raise ValueError(f"Required command is unavailable: {command}")
    destination = destination.resolve()
    relative = Path("usr/lib/x86_64-linux-gnu/openblas-pthread")
    if (destination / relative / "libopenblas.so.0").is_file():
        _validate_library(destination / relative / "libopenblas.so.0")
        return destination / relative
    if destination.exists():
        raise ValueError(f"Refusing to replace incomplete existing directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="openblas-install-", dir=destination.parent) as directory:
        temporary = Path(directory)
        subprocess.run(["apt-get", "download", "libopenblas0-pthread"], cwd=temporary, check=True)
        package, = temporary.glob("*.deb")
        staged = temporary / "runtime"
        subprocess.run(["dpkg-deb", "--extract", str(package), str(staged)], check=True)
        config = _validate_library(staged / relative / "libopenblas.so.0")
        (staged / "histra-runtime.json").write_text(json.dumps({"package": package.name, "config": config}, indent=2) + "\n")
        os.replace(staged, destination)
    return destination / relative


def _validate_library(path: Path) -> str:
    native = ctypes.CDLL(str(path))
    config = native.openblas_get_config
    config.restype = ctypes.c_char_p
    text = config().decode()
    if "USE64BITINT" in text:
        raise ValueError("SuiteSparse requires LP64 OpenBLAS; ILP64 is incompatible")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path(sys.prefix) / "native/openblas")
    args = parser.parse_args(argv)
    try:
        path = install_openblas(args.destination)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"OpenBLAS installation failed: {exc}\n")
    print(f"Project-local OpenBLAS: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
