"""Local, reproducible retrieval evaluation without sending repository data away.

The evaluator intentionally measures observable facts instead of making a
token-saving claim from a character heuristic: whether expected files are
retrieved, how much indexed source a complete task packet replaces, and the
rank at which the first expected file appears.  Case files contain only task
text and repository-relative expected paths; Brainstem never uploads them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from statistics import fmean
from typing import Any

from .indexer.graph import RepoGraph
from .retrieval.engine import RetrievalEngine
from .retrieval.task_packet import DEFAULT_PACKET_CHARS, DEFAULT_PACKET_TOTAL_CHARS, build_task_packet

EVALUATION_FORMAT_VERSION = 1
MAX_EVALUATION_CASES = 500
MAX_REQUIRED_FILES = 50


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """One human-labelled retrieval task.

    ``required_files`` is intentionally a list of files, not a generated
    answer.  It makes the ground truth reviewable and supports multiple
    necessary files for a single task.
    """

    case_id: str
    query: str
    required_files: tuple[str, ...]


def _safe_relative_path(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty repository-relative POSIX path")
    if "\\" in value:
        raise ValueError(f"{field} must use POSIX '/' separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value in {".", ""}:
        raise ValueError(f"{field} must stay inside the repository")
    return path.as_posix()


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    """Load a versioned, reviewable JSON evaluation suite.

    Format::

        {"format_version": 1, "cases": [
          {"id": "cache", "query": "where is cache invalidated?",
           "required_files": ["src/cache.py"]}
        ]}
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read evaluation cases: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Evaluation cases must be valid JSON: {exc.msg}") from exc

    if not isinstance(raw, dict) or raw.get("format_version") != EVALUATION_FORMAT_VERSION:
        raise ValueError(f"Evaluation cases must set format_version to {EVALUATION_FORMAT_VERSION}")
    entries = raw.get("cases")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Evaluation cases must contain a non-empty 'cases' list")
    if len(entries) > MAX_EVALUATION_CASES:
        raise ValueError(f"Evaluation cases may contain at most {MAX_EVALUATION_CASES} entries")

    cases: list[EvaluationCase] = []
    case_ids: set[str] = set()
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Evaluation case {number} must be an object")
        case_id = entry.get("id")
        query = entry.get("query")
        required_files = entry.get("required_files")
        if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 120:
            raise ValueError(f"Evaluation case {number} needs an id of at most 120 characters")
        if case_id in case_ids:
            raise ValueError(f"Duplicate evaluation case id: {case_id}")
        if not isinstance(query, str) or not query.strip() or len(query) > 4_000:
            raise ValueError(f"Evaluation case '{case_id}' needs a query of 1 to 4000 characters")
        if not isinstance(required_files, list) or not required_files:
            raise ValueError(f"Evaluation case '{case_id}' needs a non-empty required_files list")
        if len(required_files) > MAX_REQUIRED_FILES:
            raise ValueError(f"Evaluation case '{case_id}' has too many required files")
        validated_paths = tuple(
            _safe_relative_path(item, field=f"required_files[{index}]")
            for index, item in enumerate(required_files)
        )
        if len(set(validated_paths)) != len(validated_paths):
            raise ValueError(f"Evaluation case '{case_id}' repeats a required file")
        case_ids.add(case_id)
        cases.append(EvaluationCase(case_id=case_id, query=query.strip(), required_files=validated_paths))
    return cases


def _indexed_source_chars(repo_root: Path, graph: RepoGraph) -> int:
    """Count Unicode source characters represented by this graph only.

    ``packet_chars`` is based on Python's Unicode character count, so using
    file byte sizes here would make their ratio inaccurate for non-ASCII
    repositories.  Source parsers already decode invalid bytes with
    replacement, and the same policy keeps this metric deterministic.
    """
    root = repo_root.resolve()
    total = 0
    for relative_path in graph.files:
        try:
            candidate = (root / relative_path).resolve()
            candidate.relative_to(root)
            total += len(candidate.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
    return total


def _round(value: float) -> float:
    return round(value, 6)


def evaluate_retrieval(
    repo_root: Path,
    graph: RepoGraph,
    memory: Any,
    cases: list[EvaluationCase],
    *,
    vector_store: Any = None,
    limit: int = 5,
    max_chars: int = DEFAULT_PACKET_CHARS,
    max_packet_chars: int = DEFAULT_PACKET_TOTAL_CHARS,
) -> dict[str, Any]:
    """Evaluate retrieval and complete task-packet size against labelled cases.

    ``context_char_reduction_ratio`` compares the exact compact JSON task
    packet with the Unicode character count of indexed source. It is
    deliberately named in characters rather than tokens: model tokenizer
    measurements belong in a future adapter and must not be implied by this
    deterministic metric.
    """
    if not cases:
        raise ValueError("At least one evaluation case is required")
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    missing_from_graph = sorted(
        {path for case in cases for path in case.required_files if path not in graph.files}
    )
    if missing_from_graph:
        raise ValueError(
            "Evaluation required_files must be present in the current index: "
            + ", ".join(missing_from_graph[:10])
        )

    corpus_chars = _indexed_source_chars(repo_root, graph)
    engine = RetrievalEngine(graph, vector_store)
    results: list[dict[str, Any]] = []
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    packet_sizes: list[int] = []
    reductions: list[float] = []

    for case in cases:
        hits = engine.retrieve(case.query, limit=limit)
        retrieved_files: list[str] = []
        for hit in hits:
            if hit.file not in retrieved_files:
                retrieved_files.append(hit.file)
        required = set(case.required_files)
        matched = [path for path in retrieved_files if path in required]
        recall = len(matched) / len(required)
        first_rank = next((index for index, path in enumerate(retrieved_files, start=1) if path in required), None)
        reciprocal_rank = 1 / first_rank if first_rank else 0.0

        packet = build_task_packet(
            repo_root,
            graph,
            memory,
            case.query,
            vector_store=vector_store,
            limit=limit,
            max_chars=max_chars,
            max_packet_chars=max_packet_chars,
        )
        packet_chars = int(packet["budget"]["packet_chars"])
        reduction = 1 - (packet_chars / corpus_chars) if corpus_chars else 0.0
        recalls.append(recall)
        reciprocal_ranks.append(reciprocal_rank)
        packet_sizes.append(packet_chars)
        reductions.append(reduction)
        results.append(
            {
                "id": case.case_id,
                "required_files": list(case.required_files),
                "retrieved_files": retrieved_files,
                "matched_files": matched,
                "missing_files": [path for path in case.required_files if path not in matched],
                "recall_at_k": _round(recall),
                "first_relevant_rank": first_rank,
                "reciprocal_rank": _round(reciprocal_rank),
                "packet_chars": packet_chars,
                "context_char_reduction_ratio": _round(reduction),
            }
        )

    return {
        "evaluation_version": EVALUATION_FORMAT_VERSION,
        "method": {
            "ranking_limit": limit,
            "indexed_source_chars": corpus_chars,
            "packet_measurement": "exact compact JSON character count",
            "context_reduction_measurement": "1 - packet_chars / indexed_source_chars",
            "token_measurement": "not measured; no tokenizer or provider claim is implied",
        },
        "summary": {
            "case_count": len(results),
            "mean_recall_at_k": _round(fmean(recalls)),
            "case_hit_rate_at_k": _round(sum(recall > 0 for recall in recalls) / len(recalls)),
            "mean_reciprocal_rank": _round(fmean(reciprocal_ranks)),
            "mean_packet_chars": _round(fmean(packet_sizes)),
            "mean_context_char_reduction_ratio": _round(fmean(reductions)),
        },
        "cases": results,
    }
