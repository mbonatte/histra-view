import hashlib

import pytest

from histra.tools.release_manifest import build_manifest


def test_manifest_is_sorted_and_excludes_its_destination(tmp_path) -> None:
    (tmp_path / "z.whl").write_bytes(b"wheel")
    (tmp_path / "a.tar.gz").write_bytes(b"source")
    output = tmp_path / "SHA256SUMS"
    output.write_text("stale", encoding="utf-8")

    manifest = build_manifest(tmp_path, output)

    assert manifest.splitlines() == [
        f"{hashlib.sha256(b'source').hexdigest()}  a.tar.gz",
        f"{hashlib.sha256(b'wheel').hexdigest()}  z.whl",
    ]


def test_manifest_rejects_empty_directory(tmp_path) -> None:
    with pytest.raises(ValueError, match="No release artifacts"):
        build_manifest(tmp_path, tmp_path / "SHA256SUMS")
