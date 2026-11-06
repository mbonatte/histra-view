"""Pack existing NPZ/HDF5/JSON exports into one lossless .histra study file."""
from __future__ import annotations

import argparse
from pathlib import Path

from histra.io.bundle_conversion import pack_results_directory


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Directory containing native per-case exports")
    parser.add_argument("--output", type=Path, required=True, help="Destination .histra file")
    parser.add_argument("--model", type=Path, help="Source HRX (checked against case SHA-256 metadata)")
    parser.add_argument("--attach", action="append", default=[], type=Path, help="Embed an additional JSON/report file verbatim; repeatable")
    parser.add_argument("--overwrite", action="store_true", help="Atomically replace an existing destination")
    parser.add_argument("--remove-source", action="store_true", help="After verification, remove packed case files; use only when the producer has finished")
    args = parser.parse_args(argv)
    output = pack_results_directory(
        args.directory, args.output, model_path=args.model, attachments=args.attach,
        overwrite=args.overwrite, remove_source=args.remove_source,
    )
    print(f"Verified bundle: {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
