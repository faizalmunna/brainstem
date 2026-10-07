"""Optional native-engine boundary.

The pure Python engine is always complete and is deliberately the fallback.
This module is the only place allowed to import the separately distributed
``brainstem_native`` wheel, preventing an optional accelerator from changing
the public Python/MCP contract.
"""

from __future__ import annotations

import importlib
import hashlib
from pathlib import Path
from typing import Literal

from .indexer.graph import RepoGraph, build_graph

EngineName = Literal["auto", "native", "python"]
NATIVE_ABI_VERSION = 1


def read_utf8_sources(paths: list[Path]) -> dict[str, tuple[bytes, str]] | None:
    """Use the optional native batch reader without trusting it blindly.

    Paths arrive only from the Python walker, which already enforces manifest,
    gitignore, symlink, size, and repository-boundary rules. Native code may
    parallelize the read/UTF-8 scan, but malformed output makes us fall back
    to the portable reader rather than weakening the evidence contract.
    """
    if not paths:
        return {}
    try:
        module = importlib.import_module("brainstem_native")
        status_fn = getattr(module, "backend_status", None)
        reader = getattr(module, "read_utf8_sources", None)
        status = status_fn() if callable(status_fn) else {}
        if not isinstance(status, dict) or status.get("source_batch_reader") is not True or not callable(reader):
            return None
        expected = {str(path.resolve()) for path in paths}
        payload = reader(sorted(expected))
    except Exception:
        return None
    if not isinstance(payload, list):
        return None
    sources: dict[str, tuple[bytes, str]] = {}
    for item in payload:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return None
        raw_path, data, content_hash = item
        if not isinstance(raw_path, str) or not isinstance(data, bytes) or not isinstance(content_hash, str):
            return None
        normalized = str(Path(raw_path).resolve())
        if normalized not in expected or normalized in sources:
            return None
        # An unsigned/local wheel must not be trusted for graph evidence. The
        # rehash is intentionally retained until a signed release supplies a
        # verified integrity contract.
        if hashlib.sha256(data).hexdigest() != content_hash:
            return None
        sources[normalized] = (data, content_hash)
    return sources


def native_status() -> dict[str, object]:
    try:
        module = importlib.import_module("brainstem_native")
    except (ImportError, OSError):
        return {"available": False, "backend": "python", "reason": "brainstem-native wheel is not installed"}
    except Exception as exc:
        return {
            "available": False,
            "backend": "python",
            "reason": f"native wheel failed to load: {type(exc).__name__}",
        }
    version = getattr(module, "__version__", "unknown")
    capability = getattr(module, "backend_status", None)
    try:
        details = capability() if callable(capability) else {}
    except Exception as exc:
        return {
            "available": False,
            "backend": "python",
            "reason": f"native backend status failed: {type(exc).__name__}",
            "version": version,
        }
    details = details if isinstance(details, dict) else {}
    if details.get("ready") is not True:
        return {
            "available": False,
            "backend": "python",
            "reason": str(details.get("reason") or "installed native wheel is not ready"),
            "version": version,
            **details,
        }
    if details.get("abi_version") != NATIVE_ABI_VERSION or details.get("integrity_verified") is not True:
        return {
            "available": False,
            "backend": "python",
            "reason": "native wheel lacks a verified compatible integrity contract",
            "version": version,
            **details,
        }
    return {"available": True, "backend": "native", "version": version, **details}


def build_index(repo_root, manifest, existing: RepoGraph | None, *, engine: EngineName = "auto", workers: int | None = None) -> tuple[RepoGraph, str]:
    if engine not in {"auto", "native", "python"}:
        raise ValueError("engine must be auto, native, or python.")
    # The first native wheel contract returns a JSON-compatible RepoGraph
    # payload.  Until a matching signed wheel is installed, auto deliberately
    # runs the existing verified parser instead of compiling code at install.
    if engine != "python":
        status = native_status()
        if status["available"]:
            try:
                module = importlib.import_module("brainstem_native")
                native_build = getattr(module, "build_graph", None)
                if not callable(native_build):
                    raise RuntimeError("Installed brainstem-native wheel does not expose build_graph.")
                payload = native_build(
                    str(repo_root), manifest.model_dump_json(), existing.model_dump_json() if existing else None, workers
                )
                return RepoGraph.model_validate_json(payload), "native"
            except Exception as exc:
                if engine == "native":
                    raise RuntimeError(f"Native indexing failed: {type(exc).__name__}: {exc}") from exc
        elif engine == "native":
            raise RuntimeError(str(status["reason"]))
    return build_graph(repo_root, manifest, existing=existing), "python"
