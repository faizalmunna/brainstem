"""The deterministic symbol/dependency graph: files -> AST -> symbols -> edges.

It assembles Tree-sitter output into an embeddable, queryable, incrementally
updated graph for focused context retrieval. Import resolution is best-effort
and language-scoped: Python, JavaScript, TypeScript, Rust, Go, and Java get
intra-repository edges; C, C++, and Ruby currently provide symbols only. An
unresolved or external import is dropped rather than treated as an error.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .._atomic import atomic_write_text
from .parser import Symbol, extract_imports, extract_symbols, language_for_path
from .walker import iter_source_files

_JS_LIKE = {"javascript", "typescript", "tsx"}
_JS_EXTENSIONS_BY_LANG = {
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "tsx": [".tsx", ".ts"],
}


class FileNode(BaseModel):
    path: str  # POSIX-style, relative to repo root
    language: str | None
    content_hash: str
    symbols: list[dict[str, str | int]]
    imports: list[str] = []  # raw, as written in source


class RepoGraph(BaseModel):
    root: str
    files: dict[str, FileNode] = {}
    # resolved intra-repo dependency edges: file -> files it imports
    edges: dict[str, list[str]] = {}

    def all_symbols(self) -> list[tuple[str, dict]]:
        return [
            (path, sym)
            for path, node in self.files.items()
            for sym in node.symbols
        ]

    def find_symbol(self, name: str) -> list[tuple[str, dict]]:
        needle = name.lower()
        return [
            (path, sym)
            for path, sym in self.all_symbols()
            if needle in str(sym["name"]).lower()
        ]

    def neighbors(self, path: str) -> set[str]:
        """Files that `path` imports, plus files that import `path` --
        the one-hop dependency neighborhood used by find_related/retrieval
        to surface context a pure text/symbol match would miss."""
        out = set(self.edges.get(path, []))
        for src, targets in self.edges.items():
            if path in targets:
                out.add(src)
        out.discard(path)
        return out

    def stats(self) -> dict[str, int]:
        return {
            "files": len(self.files),
            "symbols": sum(len(n.symbols) for n in self.files.values()),
            "languages": len({n.language for n in self.files.values() if n.language}),
            "edges": sum(len(v) for v in self.edges.values()),
        }


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _module_index(files: dict[str, FileNode]) -> dict[str, str]:
    """Map dotted Python module paths -> file path, including a variant
    with a leading src-layout segment stripped, so `from brainstem.x import
    y` resolves against a `src/brainstem/x.py` layout without a manifest
    telling us about `src/`."""
    index: dict[str, str] = {}
    for path, node in files.items():
        if node.language != "python":
            continue
        stem = path[: -len(".py")] if path.endswith(".py") else path
        if stem.endswith("/__init__"):
            stem = stem[: -len("/__init__")]
        dotted = stem.replace("/", ".")
        index[dotted] = path
        parts = dotted.split(".", 1)
        if len(parts) == 2:
            index.setdefault(parts[1], path)  # src-layout-stripped variant
    return index


def _resolve_python(raw: str, module_index: dict[str, str], importing_file: str, known_files: set[str]) -> str | None:
    if not raw.startswith("."):
        return module_index.get(raw)  # absolute dotted import

    # relative import: count leading dots -> package levels to walk up from
    # the importing file's own package, per Python's `from . import x` /
    # `from ..pkg import x` semantics.
    level = len(raw) - len(raw.lstrip("."))
    remainder = raw[level:]
    if not remainder:
        return None  # bare "from . import x" -- the target is in `name`, not `module_name`; not tracked in V1

    base = Path(importing_file).parent
    for _ in range(level - 1):
        base = base.parent
    rel_path = remainder.replace(".", "/")
    for candidate in (f"{base.as_posix()}/{rel_path}.py", f"{base.as_posix()}/{rel_path}/__init__.py"):
        normalized = Path(candidate).as_posix()
        if normalized in known_files:
            return normalized
    return None


def _resolve_js(raw: str, language: str, importing_file: str, known_files: set[str]) -> str | None:
    if not raw.startswith("."):
        return None  # bare specifier (npm package) -- external, not resolvable
    base_dir = Path(importing_file).parent
    candidate_base = (base_dir / raw).as_posix()
    candidate_base = candidate_base.removeprefix("./")
    for ext in _JS_EXTENSIONS_BY_LANG.get(language, []):
        for candidate in (f"{candidate_base}{ext}", f"{candidate_base}/index{ext}"):
            normalized = Path(candidate).as_posix()
            if normalized in known_files:
                return normalized
    return None


def _resolve_rust(raw: str, known_files: set[str]) -> str | None:
    if raw.startswith("crate::"):
        rel = raw[len("crate::") :]
    elif raw.startswith("self::") or raw.startswith("super::"):
        return None  # module-relative; needs the importing file's module path to resolve, skip for V1
    else:
        return None  # external crate
    base = rel.split("::")[0].split("{")[0].strip()
    for prefix in ("src/", ""):
        for candidate in (f"{prefix}{base}.rs", f"{prefix}{base}/mod.rs"):
            if candidate in known_files:
                return candidate
    return None


def _go_module_path(repo_root: Path) -> str | None:
    """Read only the module declaration needed for local Go import mapping."""
    try:
        text = (repo_root / "go.mod").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"^\s*module\s+([^\s]+)", text, flags=re.MULTILINE)
    return match.group(1) if match else None


def _resolve_go(raw: str, module_path: str | None, known_files: set[str]) -> list[str]:
    """Resolve an import inside the current Go module to its package files.

    Go imports packages rather than a single source file. Returning the
    package's non-test files is therefore the accurate graph edge while still
    ignoring stdlib, third-party, and malformed module imports.
    """
    if not module_path or not (raw == module_path or raw.startswith(module_path + "/")):
        return []
    rel = raw.removeprefix(module_path).strip("/")
    prefix = f"{rel}/" if rel else ""
    return sorted(
        path
        for path in known_files
        if path.startswith(prefix) and path.endswith(".go") and not path.endswith("_test.go")
    )


def _resolve_java(raw: str, known_files: set[str]) -> list[str]:
    """Resolve Java imports by their package/class suffix, conservatively.

    Java source roots vary (``src/main/java``, generated roots, monorepos),
    so a full path cannot be assumed. An exact package/class suffix is stable
    across those layouts. Wildcard imports map to files in that package; static
    member imports progressively remove the member segment to find its class.
    """
    if not raw:
        return []
    wildcard = raw.endswith(".*")
    dotted = raw[:-2] if wildcard else raw
    components = dotted.split(".")
    if wildcard:
        directory_suffix = "/" + "/".join(components) + "/"
        return sorted(path for path in known_files if path.endswith(".java") and directory_suffix in f"/{path}")
    for length in range(len(components), 0, -1):
        suffix = "/".join(components[:length]) + ".java"
        matches = sorted(path for path in known_files if path.endswith(suffix))
        if matches:
            return matches
    return []


def _resolve_imports(files: dict[str, FileNode], repo_root: Path) -> dict[str, list[str]]:
    known_files = set(files.keys())
    module_index = _module_index(files)
    go_module = _go_module_path(repo_root)
    edges: dict[str, list[str]] = {}

    for path, node in files.items():
        if not node.imports:
            continue
        resolved: list[str] = []
        for raw in node.imports:
            targets: list[str] = []
            if node.language == "python":
                target = _resolve_python(raw, module_index, path, known_files)
                targets = [target] if target else []
            elif node.language in _JS_LIKE:
                target = _resolve_js(raw, node.language, path, known_files)
                targets = [target] if target else []
            elif node.language == "rust":
                target = _resolve_rust(raw, known_files)
                targets = [target] if target else []
            elif node.language == "go":
                targets = _resolve_go(raw, go_module, known_files)
            elif node.language == "java":
                targets = _resolve_java(raw, known_files)
            resolved.extend(target for target in targets if target != path)
        if resolved:
            edges[path] = sorted(set(resolved))

    return edges


def build_graph(repo_root: Path, manifest, existing: RepoGraph | None = None) -> RepoGraph:
    """Full or incremental index. If `existing` is given, files whose
    content hash hasn't changed are reused instead of re-parsed. Edges are
    always recomputed from the resulting file set, since a change to one
    file (or the addition/removal of another) can change resolution even
    for files whose own content didn't change."""
    repo_root = repo_root.resolve()
    files: dict[str, FileNode] = {}

    for path in iter_source_files(repo_root, manifest):
        rel = path.relative_to(repo_root).as_posix()
        try:
            data = path.read_bytes()
        except OSError:
            continue
        content_hash = _hash_bytes(data)

        if existing and rel in existing.files and existing.files[rel].content_hash == content_hash:
            files[rel] = existing.files[rel]
            continue

        language = language_for_path(path.suffix)
        symbols: list[Symbol] = extract_symbols(data, language) if language else []
        imports: list[str] = extract_imports(data, language) if language else []
        files[rel] = FileNode(
            path=rel,
            language=language,
            content_hash=content_hash,
            symbols=[
                {"name": s.name, "kind": s.kind, "start_line": s.start_line, "end_line": s.end_line}
                for s in symbols
            ],
            imports=imports,
        )

    graph = RepoGraph(root=str(repo_root), files=files, edges=_resolve_imports(files, repo_root))
    return graph


def save_graph(graph: RepoGraph, path: Path) -> None:
    atomic_write_text(path, graph.model_dump_json(indent=2))


def load_graph(path: Path) -> RepoGraph | None:
    if not path.exists():
        return None
    try:
        return RepoGraph.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        # An interrupted write from an older version or manual damage must not
        # crash every command. Keep the file for inspection and rebuild it on
        # the next explicit `brainstem index` call.
        return None
