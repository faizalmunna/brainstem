"""Small crash-safe persistence primitives for local Brainstem state."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _fsync_directory(directory: Path) -> None:
    """Persist a completed rename on POSIX when the filesystem supports it.

    Windows does not support opening directories with ``os.open`` in this
    form, while ``os.replace`` is already the correct atomic replacement API
    there. Directory syncing is therefore best-effort and deliberately never
    changes a successful write into a platform-specific failure.
    """
    if os.name == "nt":
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    """Replace ``path`` only after a fully flushed temporary file is ready.

    Temp and destination live in the same directory, so ``os.replace`` never
    crosses filesystems. If a write or replacement fails, the previous file is
    left untouched and the temporary file is removed. This protects indexes,
    workflow records, configuration, and SBOM output from partial writes after
    interruption or disk failures.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return path
