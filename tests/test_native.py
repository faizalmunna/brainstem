import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from brainstem.manifest import default_manifest
from brainstem.native import build_index, native_status, read_utf8_sources


def test_native_auto_is_a_safe_python_fallback_and_explicit_native_is_honest(tmp_path: Path):
    (tmp_path / "module.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    graph, backend = build_index(tmp_path, default_manifest("repo"), existing=None, engine="auto")
    assert "module.py" in graph.files
    assert backend in {"python", "native"}
    if not native_status()["available"]:
        with pytest.raises(RuntimeError, match="wheel is not installed"):
            build_index(tmp_path, default_manifest("repo"), existing=None, engine="native")


def test_native_requires_a_verified_compatible_backend_contract(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "brainstem_native",
        SimpleNamespace(__version__="0.0-test", backend_status=lambda: {"ready": True, "abi_version": 1}),
    )

    status = native_status()

    assert status["available"] is False
    assert "integrity" in str(status["reason"])


def test_auto_falls_back_when_a_verified_native_backend_fails(tmp_path: Path, monkeypatch):
    (tmp_path / "module.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    def broken_build(*_args):
        raise RuntimeError("simulated native fault")

    monkeypatch.setitem(
        sys.modules,
        "brainstem_native",
        SimpleNamespace(
            __version__="0.0-test",
            backend_status=lambda: {"ready": True, "abi_version": 1, "integrity_verified": True},
            build_graph=broken_build,
        ),
    )

    graph, backend = build_index(tmp_path, default_manifest("repo"), existing=None, engine="auto")
    assert backend == "python"
    assert "module.py" in graph.files
    with pytest.raises(RuntimeError, match="Native indexing failed"):
        build_index(tmp_path, default_manifest("repo"), existing=None, engine="native")


def test_native_source_batch_is_optional_and_validates_every_returned_digest(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.py"
    contents = b"def run():\n    return 1\n"
    source.write_bytes(contents)
    digest = __import__("hashlib").sha256(contents).hexdigest()
    monkeypatch.setitem(
        sys.modules,
        "brainstem_native",
        SimpleNamespace(
            backend_status=lambda: {"source_batch_reader": True},
            read_utf8_sources=lambda paths: [(paths[0], contents, digest)],
        ),
    )

    assert read_utf8_sources([source]) == {str(source.resolve()): (contents, digest)}


def test_native_source_batch_rejects_a_digest_mismatch(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.py"
    source.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setitem(
        sys.modules,
        "brainstem_native",
        SimpleNamespace(
            backend_status=lambda: {"source_batch_reader": True},
            read_utf8_sources=lambda paths: [(paths[0], b"x = 1\n", "not-a-digest")],
        ),
    )

    assert read_utf8_sources([source]) is None
