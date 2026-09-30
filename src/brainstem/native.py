"""Optional native-engine boundary.

The pure Python engine is always complete and is deliberately the fallback.
This module is the only place allowed to import the separately distributed
``brainstem_native`` wheel, preventing an optional accelerator from changing
the public Python/MCP contract.
"""

from __future__ import annotations

import importlib
from typing import Literal

from .indexer.graph import RepoGraph, build_graph

EngineName = Literal["auto", "native", "python"]
NATIVE_ABI_VERSION = 1


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
