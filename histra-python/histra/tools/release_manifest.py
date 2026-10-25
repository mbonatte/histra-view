"""Create a deterministic SHA-256 manifest for release artifacts."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(directory: Path, output: Path) -> str:
    root = directory.resolve()
    destination = output.resolve()
    artifacts = sorted(
        path for path in root.iterdir()
        if path.is_file() and path.resolve() != destination
    )
    if not artifacts:
        raise ValueError(f"No release artifacts found in {root}.")
    return "".join(
        f"{sha256_file(path)}  {path.name}\n" for path in artifacts
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_manifest(args.directory, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
