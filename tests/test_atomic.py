import os

import pytest

from brainstem._atomic import atomic_write_text


def test_atomic_write_replaces_complete_content(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_atomic_write_preserves_existing_file_if_replacement_fails(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text("known-good", encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated disk failure"):
        atomic_write_text(target, "partial-new-state")

    assert target.read_text(encoding="utf-8") == "known-good"
    assert not list(tmp_path.glob(".state.json.*.tmp"))
