"""Transactional local storage for Brainstem's structural repository graph.

The JSON graph remains a portable compatibility export.  SQLite is the
canonical local store because it avoids loading a large repository graph into
memory just to inspect a small neighborhood.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ..contracts import GraphEdgeV1, GraphExportV1, GraphNodeV1
from .graph import FileNode, RepoGraph

SCHEMA_VERSION = 1


def _connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection
    except BaseException:
        # SQLite can reject a corrupted database while enabling WAL. Close the
        # partially initialized handle before recovery moves the file; otherwise
        # Windows retains a lock on it.
        connection.close()
        raise


def _ensure_schema(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version not in {0, SCHEMA_VERSION}:
        raise ValueError(f"Unsupported graph store schema {version}; expected {SCHEMA_VERSION}.")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS graph_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            language TEXT,
            content_hash TEXT NOT NULL,
            symbols_json TEXT NOT NULL,
            imports_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edges (
            source_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            target_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            PRIMARY KEY (source_path, target_path)
        );
        CREATE INDEX IF NOT EXISTS edges_target_idx ON edges(target_path);
        CREATE TABLE IF NOT EXISTS symbols (
            path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            PRIMARY KEY(path, name, kind, start_line)
        );
        CREATE INDEX IF NOT EXISTS symbols_name_idx ON symbols(name COLLATE NOCASE);
        """
    )
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def save_graph_store(graph: RepoGraph, path: Path) -> None:
    """Replace one snapshot atomically inside a SQLite transaction."""
    def write_snapshot() -> None:
        with closing(_connection(path)) as connection:
            _ensure_schema(connection)
            with connection:
                connection.execute("DELETE FROM graph_metadata")
                connection.execute("DELETE FROM edges")
                connection.execute("DELETE FROM symbols")
                connection.execute("DELETE FROM files")
                connection.execute("INSERT INTO graph_metadata(key, value) VALUES (?, ?)", ("root", graph.root))
                connection.execute(
                    "INSERT INTO graph_metadata(key, value) VALUES (?, ?)", ("schema_version", str(SCHEMA_VERSION))
                )
                for file_path, node in sorted(graph.files.items()):
                    connection.execute(
                        """INSERT INTO files(path, language, content_hash, symbols_json, imports_json)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            file_path,
                            node.language,
                            node.content_hash,
                            json.dumps(node.symbols, sort_keys=True, separators=(",", ":")),
                            json.dumps(node.imports, sort_keys=True, separators=(",", ":")),
                        ),
                    )
                    for symbol in node.symbols:
                        connection.execute(
                            """INSERT INTO symbols(path, name, kind, start_line, end_line)
                               VALUES (?, ?, ?, ?, ?)""",
                            (
                                file_path,
                                str(symbol["name"]),
                                str(symbol["kind"]),
                                int(symbol["start_line"]),
                                int(symbol["end_line"]),
                            ),
                        )
                for source, targets in sorted(graph.edges.items()):
                    for target in sorted(set(targets)):
                        if source in graph.files and target in graph.files:
                            connection.execute("INSERT INTO edges(source_path, target_path) VALUES (?, ?)", (source, target))

    try:
        write_snapshot()
    except sqlite3.DatabaseError:
        if not path.exists():
            raise
        # Never discard a damaged local index. Preserve it beside the rebuilt
        # store so a user can inspect it, then reconstruct from repository
        # source on the explicit indexing operation that reached this point.
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
        path.replace(backup)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                sidecar.replace(Path(f"{backup}{suffix}"))
        write_snapshot()


def load_graph_store(path: Path) -> RepoGraph | None:
    if not path.is_file():
        return None
    try:
        with closing(_connection(path)) as connection:
            _ensure_schema(connection)
            root_row = connection.execute("SELECT value FROM graph_metadata WHERE key = 'root'").fetchone()
            if root_row is None:
                return None
            files = {
                row["path"]: FileNode(
                    path=row["path"],
                    language=row["language"],
                    content_hash=row["content_hash"],
                    symbols=json.loads(row["symbols_json"]),
                    imports=json.loads(row["imports_json"]),
                )
                for row in connection.execute(
                    "SELECT path, language, content_hash, symbols_json, imports_json FROM files ORDER BY path"
                )
            }
            edges: dict[str, list[str]] = {}
            for row in connection.execute("SELECT source_path, target_path FROM edges ORDER BY source_path, target_path"):
                edges.setdefault(row["source_path"], []).append(row["target_path"])
            return RepoGraph(root=root_row["value"], files=files, edges=edges)
    except (sqlite3.DatabaseError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        # Preserve damaged local state for inspection; the next explicit index
        # operation can rebuild it without crashing every command.
        return None


def export_graph(graph: RepoGraph, *, focus_path: str | None = None, depth: int = 1, max_nodes: int = 200) -> GraphExportV1:
    """Produce a stable, source-free, bounded graph view for agents and UI."""
    _validate_export_bounds(depth, max_nodes)
    if focus_path and focus_path not in graph.files:
        raise ValueError(f"Unknown indexed path '{focus_path}'.")
    selected = set(graph.files) if focus_path is None else {focus_path}
    if focus_path:
        frontier = {focus_path}
        reverse: dict[str, set[str]] = {}
        for source, targets in graph.edges.items():
            for target in targets:
                reverse.setdefault(target, set()).add(source)
        for _ in range(depth):
            related: set[str] = set()
            for path_item in frontier:
                related.update(graph.edges.get(path_item, []))
                related.update(reverse.get(path_item, set()))
            related -= selected
            selected.update(related)
            frontier = related
    ordered = sorted(selected)
    truncated = len(ordered) > max_nodes
    selected = set(ordered[:max_nodes])
    nodes = [
        GraphNodeV1(path=path_item, language=graph.files[path_item].language, symbol_count=len(graph.files[path_item].symbols))
        for path_item in sorted(selected)
    ]
    edges = [
        GraphEdgeV1(source=source, target=target)
        for source in sorted(selected)
        for target in sorted(graph.edges.get(source, []))
        if target in selected
    ]
    return GraphExportV1(root=graph.root, nodes=nodes, edges=edges, truncated=truncated, max_nodes=max_nodes)


def _validate_export_bounds(depth: int, max_nodes: int) -> None:
    if not 0 <= depth <= 8:
        raise ValueError("depth must be between 0 and 8.")
    if not 1 <= max_nodes <= 10_000:
        raise ValueError("max_nodes must be between 1 and 10000.")


def _chunks(values: list[str], size: int = 900) -> list[list[str]]:
    return [values[offset : offset + size] for offset in range(0, len(values), size)]


def export_graph_store(
    path: Path, *, focus_path: str | None = None, depth: int = 1, max_nodes: int = 200
) -> GraphExportV1 | None:
    """Query a bounded graph directly from SQLite without loading all files.

    Returning ``None`` means no usable SQLite snapshot exists; callers can
    then fall back to the legacy JSON export.  The traversal intentionally
    caps its working set at one node beyond the requested bound, so a highly
    connected path cannot turn a graph-view request into an unbounded query.
    """
    _validate_export_bounds(depth, max_nodes)
    if not path.is_file():
        return None
    try:
        with closing(_connection(path)) as connection:
            _ensure_schema(connection)
            root_row = connection.execute("SELECT value FROM graph_metadata WHERE key = 'root'").fetchone()
            if root_row is None:
                return None

            limit = max_nodes + 1
            truncated = False
            if focus_path:
                found = connection.execute("SELECT 1 FROM files WHERE path = ?", (focus_path,)).fetchone()
                if found is None:
                    raise ValueError(f"Unknown indexed path '{focus_path}'.")
                selected = {focus_path}
                frontier = {focus_path}
                for _ in range(depth):
                    if not frontier:
                        break
                    candidates: set[str] = set()
                    for node in sorted(frontier):
                        rows = connection.execute(
                            """SELECT target_path AS path FROM edges WHERE source_path = ?
                               UNION SELECT source_path AS path FROM edges WHERE target_path = ?
                               LIMIT ?""",
                            (node, node, limit),
                        )
                        candidates.update(row["path"] for row in rows)
                        if len(candidates) + len(selected) > max_nodes:
                            break
                    next_frontier = candidates - selected
                    remaining = max_nodes + 1 - len(selected)
                    if len(next_frontier) > remaining:
                        truncated = True
                    selected.update(sorted(next_frontier)[:remaining])
                    frontier = next_frontier
                    if len(selected) > max_nodes:
                        truncated = True
                        break
            else:
                selected = {row["path"] for row in connection.execute("SELECT path FROM files ORDER BY path LIMIT ?", (limit,))}
                truncated = len(selected) > max_nodes

            ordered = sorted(selected)[:max_nodes]
            selected = set(ordered)
            if not ordered:
                return GraphExportV1(root=root_row["value"], max_nodes=max_nodes)

            nodes_by_path: dict[str, GraphNodeV1] = {}
            for batch in _chunks(ordered):
                placeholders = ",".join("?" for _ in batch)
                for row in connection.execute(
                    # `placeholders` is generated solely from the fixed-size
                    # batch and every path remains a bound parameter.
                    f"SELECT path, language, (SELECT COUNT(*) FROM symbols WHERE symbols.path = files.path) AS symbol_count "
                    f"FROM files WHERE path IN ({placeholders})",  # nosec B608
                    batch,
                ):
                    nodes_by_path[row["path"]] = GraphNodeV1(
                        path=row["path"], language=row["language"], symbol_count=int(row["symbol_count"])
                    )
            edges: list[GraphEdgeV1] = []
            for batch in _chunks(ordered):
                placeholders = ",".join("?" for _ in batch)
                for row in connection.execute(
                    # `placeholders` is generated solely from the fixed-size
                    # batch and every path remains a bound parameter.
                    f"SELECT source_path, target_path FROM edges WHERE source_path IN ({placeholders}) ORDER BY source_path, target_path",  # nosec B608
                    batch,
                ):
                    if row["target_path"] in selected:
                        edges.append(GraphEdgeV1(source=row["source_path"], target=row["target_path"]))
            return GraphExportV1(
                root=root_row["value"],
                nodes=[nodes_by_path[path_item] for path_item in ordered if path_item in nodes_by_path],
                edges=edges,
                truncated=truncated,
                max_nodes=max_nodes,
            )
    except (sqlite3.DatabaseError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def graph_store_status(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"available": False, "path": str(path), "schema_version": None}
    try:
        with closing(_connection(path)) as connection:
            _ensure_schema(connection)
            files = int(connection.execute("SELECT COUNT(*) FROM files").fetchone()[0])
            symbols = int(connection.execute("SELECT COUNT(*) FROM symbols").fetchone()[0])
            edges = int(connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0])
            return {
                "available": True,
                "path": str(path),
                "schema_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
                "files": files,
                "symbols": symbols,
                "edges": edges,
            }
    except sqlite3.DatabaseError as exc:
        return {"available": False, "path": str(path), "schema_version": None, "error": str(exc)}
