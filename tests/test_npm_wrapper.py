"""Tests for the dependency-free npm launcher package."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required to verify the npm wrapper")
def test_npm_vendor_manifest_is_generated_and_verified_before_installation():
    npm_root = REPO_ROOT / "npm"
    sync = subprocess.run(
        ["node", "scripts/sync-vendor.js"], cwd=npm_root, capture_output=True, text=True, timeout=30, check=False
    )
    assert sync.returncode == 0, sync.stderr

    verify = subprocess.run(
        ["node", "scripts/verify-vendor.js"], cwd=npm_root, capture_output=True, text=True, timeout=30, check=False
    )
    assert verify.returncode == 0, verify.stderr
    assert "verified" in verify.stdout
    assert (npm_root / "vendor" / ".brainstem-integrity.json").is_file()
