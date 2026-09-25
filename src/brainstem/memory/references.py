"""Safe conversion of user-selected indexed paths into memory provenance."""

from __future__ import annotations

from pathlib import PurePosixPath

from ..indexer.graph import RepoGraph


def references_from_csv(graph: RepoGraph | None, paths: str) -> list[tuple[str, str]]:
    """Resolve comma-separated repository paths to current graph hashes.

    The caller can persist only paths already in the index; this prevents a
    memory entry from claiming provenance outside the target repository or
    from storing arbitrary source text.
    """
    requested = [item.strip() for item in paths.split(",") if item.strip()]
    if not requested:
        return []
    if graph is None:
        raise ValueError("Source references require an index. Run `brainstem index` first.")

    references: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in requested:
        normalized = PurePosixPath(raw.replace("\\", "/"))
        path = normalized.as_posix()
        if (
            normalized.is_absolute()
            or ".." in normalized.parts
            or ":" in path
            or path not in graph.files
        ):
            raise ValueError(f"Reference path must be an indexed repository file: {raw!r}")
        if path not in seen:
            seen.add(path)
            references.append((path, graph.files[path].content_hash))
    return references
