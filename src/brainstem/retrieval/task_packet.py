"""Explainable, local task-context compilation.

``prepare_task`` is the product-level composition over the existing graph,
bounded source bundles, project memory, and repository state.  It does not
call a model and it never persists a prompt or source excerpt.  Its job is to
make the evidence supplied to a host agent small, inspectable, and fresh
enough for the agent to decide what to do next.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from ..indexer.graph import RepoGraph
from .context import MAX_BUNDLE_HITS, MIN_BUNDLE_CHARS, build_context_bundle
from .engine import RetrievalEngine, RetrievalHit

PACKET_VERSION = 1
DEFAULT_PACKET_CHARS = 8_000
DEFAULT_PACKET_TOTAL_CHARS = 12_000
MIN_PACKET_TOTAL_CHARS = 6_000
MAX_PACKET_TOTAL_CHARS = 32_000
MAX_TASK_CHARS = 4_000
MAX_RULES = 10
MAX_MEMORIES = 5
MAX_IMPACT_NEIGHBORS = 12
MAX_TEST_CANDIDATES = 10
MAX_MEMORY_TEXT_CHARS = 1_200
MAX_LANDMARKS = 12

_SENSITIVE_FILENAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "secrets"}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_RISK_KEYWORDS = {
    "authentication": "authentication or authorization",
    "authorization": "authentication or authorization",
    "auth": "authentication or authorization",
    "login": "authentication or authorization",
    "signin": "authentication or authorization",
    "permission": "permissions",
    "secret": "secrets or credentials",
    "credential": "secrets or credentials",
    "payment": "payment or billing",
    "billing": "payment or billing",
    "migration": "database migration",
    "database": "database or data persistence",
    "deploy": "deployment",
    "security": "security-sensitive code",
}
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth(?:orization)?|bearer|credential|password|secret|token)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+([a-z0-9._~+/-]{8,})")
_ENTRY_FILENAMES = {
    "main.py", "main.go", "main.rs", "main.java", "index.js", "index.ts", "index.tsx",
    "app.py", "server.py", "server.js", "server.ts", "server.tsx", "manage.py",
}
_ENTRY_SYMBOLS = {"main", "create_app", "create_server", "bootstrap"}
_BUILD_FILES = (
    "pyproject.toml", "package.json", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "Cargo.toml", "Makefile", "docker-compose.yml", "compose.yml",
)


def _looks_sensitive(path: str) -> bool:
    candidate = Path(path)
    name = candidate.name.lower()
    return (
        (name.startswith(".env") and not name.endswith(".example"))
        or name in _SENSITIVE_FILENAMES
        or candidate.suffix.lower() in _SENSITIVE_SUFFIXES
    )


def _content_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _redact_and_bound(text: Any) -> str:
    """Prevent a remembered secret or long transcript entering model context."""
    value = str(text)
    value = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    if len(value) > MAX_MEMORY_TEXT_CHARS:
        return value[:MAX_MEMORY_TEXT_CHARS] + "… [truncated]"
    return value


def _safe_fact(fact: dict[str, Any]) -> dict[str, Any]:
    """Return only small, redacted memory fields suitable for an AI packet."""
    return {
        key: _redact_and_bound(fact[key]) if key in {"title", "body", "tags"} else fact[key]
        for key in ("id", "kind", "title", "body", "tags", "created_at", "scope")
        if key in fact
    }


def _git_state(repo_root: Path) -> dict[str, Any]:
    """Return bounded, metadata-only local Git state.

    Git is optional: a normal directory or an unavailable executable simply
    produces an empty, known state.  Paths matching the source-bundle secret
    exclusions are deliberately not disclosed to an MCP client.
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "changed_files": [], "untracked_files": [], "sensitive_omitted": 0}
    if proc.returncode != 0:
        return {"available": False, "changed_files": [], "untracked_files": [], "sensitive_omitted": 0}

    changed: list[str] = []
    untracked: list[str] = []
    sensitive_omitted = 0
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        status, path = line[:2], line[3:]
        # The destination is what matters for a rename in a task packet.
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        if _looks_sensitive(path):
            sensitive_omitted += 1
            continue
        target = untracked if status == "??" else changed
        if len(target) < 50:
            target.append(path)
    return {
        "available": True,
        "changed_files": changed,
        "untracked_files": untracked,
        "sensitive_omitted": sensitive_omitted,
    }


def _task_git_state(git_state: dict[str, Any], relevant_files: set[str]) -> dict[str, Any]:
    """Keep the task packet focused even when a repository is broadly dirty."""
    changed = git_state["changed_files"]
    untracked = git_state["untracked_files"]
    return {
        "available": git_state["available"],
        "changed_files": [path for path in changed if path in relevant_files],
        "untracked_files": [path for path in untracked if path in relevant_files],
        "changed_file_count": len(changed),
        "untracked_file_count": len(untracked),
        "sensitive_omitted": git_state["sensitive_omitted"],
    }


def _context_manifest(graph: RepoGraph, excerpts: list[dict[str, Any]]) -> dict[str, Any]:
    files = [
        {
            "file": excerpt["file"],
            "content_hash": graph.files[excerpt["file"]].content_hash,
            "start_line": excerpt["start_line"],
            "end_line": excerpt["end_line"],
            "char_count": excerpt["char_count"],
        }
        for excerpt in excerpts
        if excerpt["file"] in graph.files
    ]
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    return {"index_fingerprint": fingerprint, "files": files}


def _freshness(repo_root: Path, graph: RepoGraph, excerpts: list[dict[str, Any]]) -> dict[str, Any]:
    stale_files: list[str] = []
    missing_files: list[str] = []
    root = repo_root.resolve()
    for excerpt in excerpts:
        path = excerpt["file"]
        node = graph.files.get(path)
        if node is None:
            continue
        try:
            candidate = (root / path).resolve()
            candidate.relative_to(root)
        except (OSError, ValueError):
            missing_files.append(path)
            continue
        current = _content_hash(candidate)
        if current is None:
            missing_files.append(path)
        elif current != node.content_hash:
            stale_files.append(path)
    return {
        "index_current_for_packet": not stale_files and not missing_files,
        "stale_files": stale_files,
        "missing_files": missing_files,
    }


def _impact_neighbors(graph: RepoGraph, hits: list[RetrievalHit], excerpt_files: set[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen = set(excerpt_files)
    for hit in hits:
        if hit.file not in graph.files:
            continue
        imported = set(graph.edges.get(hit.file, []))
        for neighbor in sorted(graph.neighbors(hit.file)):
            if neighbor in seen or neighbor not in graph.files:
                continue
            seen.add(neighbor)
            direction = "imports" if neighbor in imported else "imported_by"
            result.append(
                {
                    "file": neighbor,
                    "relationship": direction,
                    "via": hit.file,
                    "language": graph.files[neighbor].language or "unknown",
                }
            )
            if len(result) >= MAX_IMPACT_NEIGHBORS:
                return result
    return result


def _is_test_file(path: str) -> bool:
    name = Path(path).name.lower()
    parts = {part.lower() for part in Path(path).parts}
    return name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")) or bool(
        {"test", "tests", "__tests__"} & parts
    )


def _test_candidates(graph: RepoGraph, hits: list[RetrievalHit]) -> list[dict[str, str]]:
    direct_files = {hit.file for hit in hits}
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in sorted(graph.files):
        if not _is_test_file(path):
            continue
        normalized = path.lower().replace("test_", "").replace("_test", "")
        reason = "test file matched by task retrieval" if path in direct_files else "test file related by module name"
        related = path in direct_files or any(Path(source).stem.lower() in normalized for source in direct_files)
        if related and path not in seen:
            seen.add(path)
            candidates.append({"file": path, "reason": reason})
        if len(candidates) >= MAX_TEST_CANDIDATES:
            break
    return candidates


def _project_landmarks(repo_root: Path, graph: RepoGraph) -> dict[str, list[Any]]:
    """Return compact structural orientation when task retrieval is broad.

    These are deterministic names and graph facts, never generated summaries.
    Configuration is disclosed as filenames only because build configuration can
    legitimately contain secrets or deployment metadata.
    """
    entry_points: list[dict[str, str]] = []
    test_roots: set[str] = set()
    source_roots: Counter[str] = Counter()
    for path, node in sorted(graph.files.items()):
        parts = Path(path).parts
        if parts:
            source_roots[parts[0]] += 1
        if _is_test_file(path):
            parent = Path(path).parent.as_posix()
            test_roots.add("." if parent == "." else parent)
        if Path(path).name.lower() in _ENTRY_FILENAMES:
            entry_points.append({"file": path, "reason": "conventional entry filename"})
        for symbol in node.symbols:
            if str(symbol["name"]).lower() in _ENTRY_SYMBOLS:
                entry_points.append(
                    {
                        "file": path,
                        "symbol": str(symbol["name"]),
                        "reason": "conventional entry symbol",
                    }
                )
    build_files = [name for name in _BUILD_FILES if (repo_root / name).is_file()]
    return {
        "entry_points": entry_points[:MAX_LANDMARKS],
        "test_roots": sorted(test_roots)[:MAX_LANDMARKS],
        "source_roots": [
            {"path": path, "indexed_files": count}
            for path, count in source_roots.most_common(MAX_LANDMARKS)
        ],
        "build_files": build_files,
    }


def _risk_signals(task: str, excerpts: list[dict[str, Any]], git_state: dict[str, Any]) -> list[str]:
    haystack = " ".join(
        [task, *(excerpt["file"] for excerpt in excerpts), *git_state["changed_files"]]
    ).lower()
    signals = sorted({label for keyword, label in _RISK_KEYWORDS.items() if keyword in haystack})
    if git_state["changed_file_count"] or git_state["untracked_file_count"]:
        signals.append("working tree has uncommitted changes")
    return signals


def _reference_is_current(repo_root: Path, graph: RepoGraph, reference: dict[str, str]) -> bool:
    path = reference["path"]
    node = graph.files.get(path)
    if node is None or node.content_hash != reference["content_hash"]:
        return False
    root = repo_root.resolve()
    try:
        candidate = (root / path).resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return False
    return _content_hash(candidate) == reference["content_hash"]


def _memory_for_task(memory: Any, task: str, repo_root: Path, graph: RepoGraph) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Memory search is intentionally conservative: exact task phrases only.

    A context packet must not turn a vague word match into stale or unrelated
    project instruction.  Rules are included separately because they are
    explicit repository policy.
    """
    included: list[dict[str, Any]] = []
    freshness = {"current": 0, "unverified": 0, "stale_omitted": 0}
    for fact in memory.search(task, limit=MAX_MEMORIES):
        references = memory.references(int(fact["id"]))
        if references and not all(_reference_is_current(repo_root, graph, reference) for reference in references):
            freshness["stale_omitted"] += 1
            continue
        safe = _safe_fact(fact)
        if references:
            freshness["current"] += 1
            safe["freshness"] = "current"
            safe["references"] = references
        else:
            freshness["unverified"] += 1
            safe["freshness"] = "unverified"
        included.append(safe)
    return included, freshness


def _serialized_chars(value: dict[str, Any]) -> int:
    """Use the exact JSON payload size, not a source-only approximation."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _empty_bundle(hits: list[RetrievalHit]) -> dict[str, Any]:
    return {
        "excerpts": [],
        "total_chars": 0,
        "truncated": bool(hits),
        "skipped": 0,
        "sensitive_skipped": 0,
        "deduplicated": 0,
    }


def _compact_auxiliary(packet: dict[str, Any], total_budget: int) -> int:
    """Drop lowest-priority metadata only after source was reduced first."""
    evidence = packet["evidence"]
    landmarks = packet["project_landmarks"]
    git_state = packet["repository_state"]["git"]
    # Repository policy remains longest because it is more important than a
    # speculative test/neighbor hint. Every omission is counted in `budget`.
    collections = [
        evidence["memory"],
        evidence["test_candidates"],
        evidence["impact_neighbors"],
        landmarks["entry_points"],
        landmarks["test_roots"],
        landmarks["source_roots"],
        landmarks["build_files"],
        git_state["changed_files"],
        git_state["untracked_files"],
        evidence["rules"],
    ]
    omitted = 0
    for collection in collections:
        while collection and _serialized_chars(packet) > total_budget:
            collection.pop()
            omitted += 1
    return omitted


def build_task_packet(
    repo_root: Path,
    graph: RepoGraph,
    memory: Any,
    task: str,
    *,
    vector_store: Any = None,
    limit: int = 5,
    max_chars: int = DEFAULT_PACKET_CHARS,
    max_packet_chars: int = DEFAULT_PACKET_TOTAL_CHARS,
) -> dict[str, Any]:
    """Compile the smallest inspectable evidence packet for ``task``.

    The function is side-effect-free.  It deliberately returns current source
    excerpts plus a freshness warning when the stored index is stale; callers
    can then re-index before relying on graph-derived impact information.
    """
    task = task.strip()
    if not task:
        raise ValueError("task must not be empty")
    if len(task) > MAX_TASK_CHARS:
        raise ValueError(f"task must be at most {MAX_TASK_CHARS} characters")
    if not 1 <= limit <= MAX_BUNDLE_HITS:
        raise ValueError(f"limit must be between 1 and {MAX_BUNDLE_HITS}")
    if not MIN_PACKET_TOTAL_CHARS <= max_packet_chars <= MAX_PACKET_TOTAL_CHARS:
        raise ValueError(f"max_packet_chars must be between {MIN_PACKET_TOTAL_CHARS} and {MAX_PACKET_TOTAL_CHARS}")

    engine = RetrievalEngine(graph, vector_store)
    hits = engine.retrieve(task, limit=limit)

    def assemble(source_budget: int) -> dict[str, Any]:
        bundle = build_context_bundle(repo_root, hits, max_chars=source_budget) if source_budget else _empty_bundle(hits)
        excerpts = bundle["excerpts"]
        excerpt_files = {excerpt["file"] for excerpt in excerpts}
        selected = [hit for hit in hits if hit.file in excerpt_files]
        raw_git_state = _git_state(repo_root)
        impact_neighbors = _impact_neighbors(graph, selected, excerpt_files)
        related_files = excerpt_files | {item["file"] for item in impact_neighbors}
        git_state = _task_git_state(raw_git_state, related_files)
        freshness = _freshness(repo_root, graph, excerpts)
        rules = [_safe_fact(fact) for fact in memory.list(kind="rule", limit=MAX_RULES)]
        memories, memory_freshness = _memory_for_task(memory, task, repo_root, graph)
        risk_signals = _risk_signals(task, excerpts, git_state)

        warnings: list[str] = []
        if not freshness["index_current_for_packet"]:
            warnings.append("The source bundle is current, but graph metadata is stale; run `brainstem index` before relying on impact analysis.")
        if bundle["sensitive_skipped"]:
            warnings.append("Sensitive files were excluded from the source bundle.")
        if not excerpts:
            warnings.append("No safe source excerpts matched this task. Refine the task or inspect project landmarks before changing code.")
        if memory_freshness["stale_omitted"]:
            warnings.append("Stale hash-bound memory was omitted from this task packet.")

        return {
            "packet_version": PACKET_VERSION,
            "task": task,
            "evidence": {
                "excerpts": excerpts,
                "selected": [
                    {
                        "file": hit.file,
                        "symbol": hit.symbol,
                        "kind": hit.kind,
                        "line": hit.line,
                        "score": round(hit.score, 4),
                        "reason": hit.reason,
                    }
                    for hit in selected
                ],
                "impact_neighbors": impact_neighbors,
                "test_candidates": _test_candidates(graph, selected),
                "rules": rules,
                "memory": memories,
                "memory_freshness": memory_freshness,
            },
            "project_landmarks": _project_landmarks(repo_root, graph),
            "repository_state": {"git": git_state, "freshness": freshness},
            "risk_signals": risk_signals,
            "budget": {
                "source_chars": bundle["total_chars"],
                "source_budget_chars": source_budget,
                "requested_source_budget_chars": max_chars,
                "packet_budget_chars": max_packet_chars,
                "excerpts": len(excerpts),
                "truncated": bundle["truncated"],
                "sensitive_skipped": bundle["sensitive_skipped"],
                "overlapping_excerpts_deduplicated": bundle["deduplicated"],
            },
            "context_manifest": _context_manifest(graph, excerpts),
            "recommended_next_actions": [
                "Review the selected source evidence before editing.",
                "Run `brainstem index` if freshness reports stale graph metadata.",
                "Expand context only for a named missing dependency, symbol, or test.",
                "Start a workflow before implementing a non-trivial or risk-signalled change.",
            ],
            "warnings": warnings,
        }

    source_budget = max_chars
    packet = assemble(source_budget)
    while _serialized_chars(packet) > max_packet_chars and source_budget:
        overflow = _serialized_chars(packet) - max_packet_chars
        source_budget = max(0, source_budget - max(overflow * 2, MIN_BUNDLE_CHARS))
        if 0 < source_budget < MIN_BUNDLE_CHARS:
            source_budget = 0
        packet = assemble(source_budget)

    source_trimmed = source_budget != max_chars
    if source_trimmed:
        packet["warnings"].append("Evidence was trimmed to honor the whole-packet context budget.")
    # Include accounting fields in the measured payload before doing the final
    # trim; otherwise a near-limit packet could exceed its advertised cap.
    packet["budget"]["auxiliary_items_omitted"] = 0
    packet["budget"]["packet_chars"] = 0
    auxiliary_omitted = _compact_auxiliary(packet, max_packet_chars)
    if auxiliary_omitted and not source_trimmed:
        packet["warnings"].append("Evidence was trimmed to honor the whole-packet context budget.")
        auxiliary_omitted += _compact_auxiliary(packet, max_packet_chars)
    packet["budget"]["auxiliary_items_omitted"] = auxiliary_omitted
    for _ in range(3):
        packet["budget"]["packet_chars"] = _serialized_chars(packet)
    return packet
