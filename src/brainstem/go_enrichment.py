"""Opt-in, network-disabled Go build-aware graph enrichment.

Brainstem's normal parser never needs Go.  This module runs only when the
user explicitly asks for ``--go-semantics`` and never invokes ``go test``,
``go generate``, or project binaries.  A future signed Go analyzer may add
type-reference facts through the same result contract.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .indexer.graph import RepoGraph

_TIMEOUT_S = 20


def _go_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    # Never fetch a module while analyzing a repository. Cached/vendor
    # dependencies may be used; unavailable ones make enrichment unavailable.
    env["GOPROXY"] = "off"
    env["GOSUMDB"] = "off"
    env["GONOSUMDB"] = "*"
    # Do not let analysis load a user Go environment, workspace overlay, or
    # automatically download a newer toolchain. This keeps the operation
    # limited to the installed Go binary, the repository module, and already
    # available local dependencies.
    env["GOENV"] = "off"
    env["GOWORK"] = "off"
    env["GOTOOLCHAIN"] = "local"
    # Do not inherit GOFLAGS: it can carry build tags, module-changing flags,
    # or an execution wrapper that makes an opt-in graph read less safe.
    env["GOFLAGS"] = "-mod=readonly"
    return env


def go_semantics_status(repo_root: Path) -> dict[str, object]:
    executable = shutil.which("go")
    if executable is None:
        return {"available": False, "reason": "Go toolchain is not installed"}
    try:
        version = subprocess.run(
            [executable, "version"], cwd=repo_root, env=_go_env(repo_root), text=True, capture_output=True, timeout=_TIMEOUT_S
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": f"Unable to execute Go: {exc}"}
    if version.returncode != 0:
        return {"available": False, "reason": version.stderr.strip() or "go version failed"}
    if not (repo_root / "go.mod").is_file():
        return {"available": False, "reason": "Repository has no go.mod"}
    return {"available": True, "version": version.stdout.strip(), "network": "disabled"}


def _decode_json_stream(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    cursor = 0
    values: list[dict] = []
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            break
        value, cursor = decoder.raw_decode(text, cursor)
        if isinstance(value, dict):
            values.append(value)
    return values


def enrich_go_graph(repo_root: Path, graph: RepoGraph) -> dict[str, object]:
    status = go_semantics_status(repo_root)
    if not status["available"]:
        return {**status, "graph": graph, "edges_added": 0}
    executable = shutil.which("go")
    assert executable is not None
    try:
        result = subprocess.run(
            [executable, "list", "-e", "-json", "./..."],
            cwd=repo_root,
            env=_go_env(repo_root),
            text=True,
            capture_output=True,
            timeout=_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": f"Go package inspection failed: {exc}", "graph": graph, "edges_added": 0}
    if result.returncode != 0:
        return {
            "available": False,
            "reason": result.stderr.strip() or "go list failed with network disabled",
            "graph": graph,
            "edges_added": 0,
        }
    packages = _decode_json_stream(result.stdout)
    module_file = repo_root / "go.mod"
    module = next(
        (line.split(maxsplit=1)[1].strip() for line in module_file.read_text(encoding="utf-8").splitlines() if line.startswith("module ")),
        "",
    )
    if not module:
        return {"available": False, "reason": "Unable to read Go module name", "graph": graph, "edges_added": 0}

    package_files: dict[str, list[str]] = {}
    for package in packages:
        import_path, directory = package.get("ImportPath"), package.get("Dir")
        if not isinstance(import_path, str) or not isinstance(directory, str):
            continue
        try:
            relative_directory = Path(directory).resolve().relative_to(repo_root.resolve())
        except ValueError:
            continue
        files = [
            (relative_directory / name).as_posix()
            for name in package.get("GoFiles", [])
            if isinstance(name, str) and (relative_directory / name).as_posix() in graph.files
        ]
        if files:
            package_files[import_path] = files

    added = 0
    for package in packages:
        import_path = package.get("ImportPath")
        sources = package_files.get(import_path, []) if isinstance(import_path, str) else []
        if not sources:
            continue
        for dependency in package.get("Imports", []):
            if not isinstance(dependency, str) or not (dependency == module or dependency.startswith(module + "/")):
                continue
            targets = package_files.get(dependency, [])
            for source in sources:
                prior = set(graph.edges.get(source, []))
                merged = sorted((prior | set(targets)) - {source})
                added += len(set(merged) - prior)
                if merged:
                    graph.edges[source] = merged
    return {"available": True, "reason": "network-disabled Go build graph", "graph": graph, "edges_added": added, **status}
