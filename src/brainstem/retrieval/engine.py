"""Deterministic-first retrieval: given a question, return the smallest
relevant slice of the repo graph.

Ranking here is exact/substring symbol matches first, then a naive
term-overlap score against symbol and path tokens, with a graph-weighted
ranking (using the real dependency-edge graph, see indexer/graph.py's
module docstring) as a reasonable V2 upgrade.

A VectorStore adapter can be layered in later to re-rank or supplement
these results (adapters/base.py); it is intentionally not required to run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..indexer.graph import RepoGraph

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
# Splits a run of letters/digits on camelCase/PascalCase/acronym boundaries,
# e.g. "RequestCache" -> ["Request", "Cache"], "HTTPServer" -> ["HTTP",
# "Server"]. Without this, a query for "request cache" (two words) never
# matched a symbol named RequestCache (one opaque lowercased token) -- this
# was a real bug caught by retrieval evaluation: precision
# was ~0.05 before this fix because test-file symbol names with underscores
# (already split by _TOKEN_RE) out-competed the actual PascalCase-named
# implementation classes they were testing.
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

# Filler words that inflate the query-token denominator without adding
# signal -- "how is the request cache implemented" and "request cache"
# should score the same file, not the first one worse for having more
# words in it.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "how", "what", "where", "when", "why", "who", "which",
    "do", "does", "did", "doing",
    "of", "to", "in", "on", "at", "for", "with", "by", "from", "as",
    "and", "or", "this", "that", "it", "its",
}

# A graph's symbols and paths are a fast, explainable first pass, but they do
# not contain words used only in a function body or its comments.  The bounded
# fallback below fills that gap without storing extra source-derived terms in
# the on-disk index.  That matters for both privacy (the index is not a second
# copy of source text) and predictable interactive latency.
MAX_CONTENT_FALLBACK_FILES = 500
MAX_CONTENT_FALLBACK_BYTES = 2_000_000
MAX_CONTENT_FALLBACK_FILE_BYTES = 256_000
MIN_CONTENT_MATCHES = 2
_SENSITIVE_FILENAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "secrets"}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_TEST_PATH_PARTS = {"test", "tests", "spec", "specs", "__tests__"}
_TEST_QUERY_TERMS = {"test", "tests", "regression", "coverage", "assert", "verify", "validation", "spec", "specs"}
_SUPPORT_PATH_PARTS = _TEST_PATH_PARTS | {"example", "examples", "doc", "docs", "benchmark", "benchmarks"}
# Small, code-idiom expansions are used only by the bounded source-text
# fallback.  They bridge common natural-language/API vocabulary without
# polluting deterministic symbol/path ranking or pretending to be a semantic
# model.  Each original query term remains one scoring group, so aliases do
# not inflate a file's score.
_CONTENT_QUERY_ALIASES = {
    "request": {"req"},
    "response": {"res"},
    "dispatch": {"handle", "handler"},
    "dispatched": {"handle", "handler"},
    "dispatcher": {"handle", "handler"},
    "register": {"registered", "registration", "use", "mount"},
    "registered": {"register", "registration", "use", "mount"},
    "registration": {"register", "registered", "use", "mount"},
    "middleware": {"router", "interceptor", "filter"},
    "route": {"router", "routing"},
    "routing": {"route", "router"},
    "validate": {"validation", "validator"},
    "validation": {"validate", "validator"},
    "authenticate": {"authentication", "authorize"},
    "authentication": {"authenticate", "authorize"},
    "authorize": {"authorization", "permission"},
    "authorization": {"authorize", "permission"},
}


def _tokenize(text: str, filter_stopwords: bool = False) -> set[str]:
    tokens: set[str] = set()
    for word in _TOKEN_RE.findall(text):
        for part in _CAMEL_RE.findall(word):
            tokens.add(part.lower())
    if filter_stopwords:
        tokens -= _STOPWORDS
    return tokens


# Longest-suffix-first. "tion"/"te" are paired deliberately so
# "authentication" (-tion -> "authentica") and "authenticate" (-te ->
# "authenticat"... no: both must reduce to the SAME stem, see _stem's
# docstring) land together -- "ate"/"ation" is the actual verb/noun pair
# to strip, not "e"/"ation" alone.
_STEM_SUFFIXES = ("ations", "ation", "ating", "ated", "ate", "ing", "es", "ed", "s")


def _stem(token: str) -> str:
    """Crude suffix-stripping stem that normalizes common verb/noun
    derivational pairs to the same root, e.g. "authentication",
    "authenticate", "authenticated", "authenticating" all -> "authenticat".
    Not linguistically rigorous (no real Porter-stemmer algorithm, no
    irregular forms) -- just enough to close the single most common gap in
    deterministic-only retrieval: a question phrased with a noun form
    ("where is authentication handled?") failing to match a symbol named
    with the verb form (`authenticate`). The README's own quickstart
    example hit exactly this before the fix, returning zero results with
    --no-semantic."""
    # A final silent ``e`` is normally retained in an infinitive but lost
    # before ``-ed``: ``resolve`` -> ``resolved`` and ``save`` -> ``saved``.
    # Restoring it for the unambiguous ``v`` case lets a question phrased in
    # the past tense find the implementation symbol without broad fuzzy
    # matching (which would make rankings less explainable).
    if len(token) > 5 and token.endswith("ved"):
        return token[:-1]

    for suffix in _STEM_SUFFIXES:
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _overlap(query_tokens: set[str], other_tokens: set[str]) -> set[str]:
    """Token overlap tolerant of simple plural/singular mismatches, e.g.
    "permissions" (query) vs "permission" (symbol name Permission,
    PermissionDenied, require_permission). Exact set intersection missed
    this in practice: a permissions-enforcement task scored 0 precision/recall
    without it,
    because every relevant symbol/file used the singular form. Falls back
    to crude stemming (_stem) for verb/noun-form mismatches plurals alone
    don't cover, e.g. "authentication" vs "authenticate"."""
    matched = query_tokens & other_tokens
    remaining = query_tokens - matched
    for token in list(remaining):
        if (token.endswith("s") and token[:-1] in other_tokens) or f"{token}s" in other_tokens:
            matched.add(token)
            remaining.discard(token)
    if remaining:
        other_stems = {_stem(t) for t in other_tokens}
        for token in remaining:
            if _stem(token) in other_stems:
                matched.add(token)
    return matched


def _content_query_groups(query_tokens: set[str]) -> dict[str, set[str]]:
    """Build one source-match group per original query term.

    Keeping groups separate means a file mentioning both ``router`` and
    ``use`` earns one match for a user's single ``middleware`` term, rather
    than incorrectly looking twice as relevant.
    """
    return {
        token: {token, *_CONTENT_QUERY_ALIASES.get(token, set())}
        for token in query_tokens
    }


def _content_overlap(groups: dict[str, set[str]], source_tokens: set[str]) -> set[str]:
    return {term for term, variants in groups.items() if variants & source_tokens}


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    file: str
    symbol: str | None
    kind: str | None
    line: int | None
    score: float
    reason: str


class RetrievalEngine:
    def __init__(self, graph: RepoGraph, vector_store=None, *, repo_root: Path | None = None) -> None:
        self.graph = graph
        # Deterministic retrieval works fully with vector_store=None. When
        # available, vectors only add candidates the lexical/graph passes
        # missed; they never replace the explainable base ranking.
        self.vector_store = vector_store
        self.repo_root = repo_root.resolve() if repo_root is not None else None

    @staticmethod
    def _is_sensitive_path(path: Path) -> bool:
        name = path.name.lower()
        return (
            (name.startswith(".env") and not name.endswith(".example"))
            or name in _SENSITIVE_FILENAMES
            or path.suffix.lower() in _SENSITIVE_SUFFIXES
        )

    @staticmethod
    def _is_test_path(path: str) -> bool:
        return bool(_TEST_PATH_PARTS & {part.lower() for part in Path(path).parts})

    @staticmethod
    def _is_support_path(path: str) -> bool:
        return bool(_SUPPORT_PATH_PARTS & {part.lower() for part in Path(path).parts})

    def _content_hits(self, query_tokens: set[str]) -> list[RetrievalHit]:
        """Return bounded, non-persistent source-text candidates.

        This deliberately runs only when the caller supplied a repository
        root.  Callers that hold graph metadata alone retain the original
        symbols/path-only behavior.  Files are resolved under that root,
        sensitive names are skipped, and both per-file and total read budgets
        make the fallback safe for interactive use on large repositories.
        """
        if self.repo_root is None or len(query_tokens) < MIN_CONTENT_MATCHES:
            return []

        root = self.repo_root
        groups = _content_query_groups(query_tokens)
        scanned_files = 0
        scanned_bytes = 0
        asks_for_tests = bool(query_tokens & _TEST_QUERY_TERMS)
        hits: list[RetrievalHit] = []
        for rel in sorted(self.graph.files):
            if scanned_files >= MAX_CONTENT_FALLBACK_FILES or scanned_bytes >= MAX_CONTENT_FALLBACK_BYTES:
                break
            try:
                candidate = (root / rel).resolve()
                candidate.relative_to(root)
                size = candidate.stat().st_size
            except (OSError, ValueError):
                continue
            if (
                not candidate.is_file()
                or self._is_sensitive_path(candidate)
                or size > MAX_CONTENT_FALLBACK_FILE_BYTES
                or scanned_bytes + size > MAX_CONTENT_FALLBACK_BYTES
            ):
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "\x00" in text:
                continue
            scanned_files += 1
            scanned_bytes += size
            overlap = _content_overlap(groups, _tokenize(text))
            if len(overlap) < MIN_CONTENT_MATCHES:
                continue

            # Prefer exact vocabulary overlap in production code for a normal
            # implementation question.  A test remains eligible, and loses
            # that small preference only when the question itself is not
            # asking for test/verification work.
            score = 1.0 + 1.2 * (len(overlap) / len(query_tokens))
            if not asks_for_tests and self._is_support_path(rel):
                # Examples/docs can explain an API and tests can verify it,
                # but an implementation request should inspect production
                # code first when it offers equivalent vocabulary coverage.
                score -= 0.6 if self._is_test_path(rel) else 0.4

            line = next(
                (
                    number
                    for number, source_line in enumerate(text.splitlines(), start=1)
                    if len(_content_overlap(groups, _tokenize(source_line))) >= 2
                ),
                1,
            )
            hits.append(
                RetrievalHit(
                    file=rel,
                    symbol=None,
                    kind=None,
                    line=line,
                    score=score,
                    reason="bounded source text match",
                )
            )
        return hits

    def retrieve(self, query: str, limit: int = 10) -> list[RetrievalHit]:
        query_tokens = _tokenize(query, filter_stopwords=True)
        if not query_tokens:
            return []

        hits: list[RetrievalHit] = []

        # Pass 0: query is (or contains) a known file path -- pull in its
        # direct dependency neighbors (imports it / is imported by it).
        # This is what makes find_related useful for "what else touches
        # this file" rather than only lexical overlap.
        for path in self.graph.files:
            if path in query or path.rsplit("/", 1)[-1] in query:
                for neighbor in self.graph.neighbors(path):
                    hits.append(
                        RetrievalHit(
                            file=neighbor,
                            symbol=None,
                            kind=None,
                            line=None,
                            score=0.9,
                            reason=f"dependency neighbor of {path}",
                        )
                    )

        # Pass 1: exact/substring symbol name matches -- highest confidence.
        # Scored symmetrically (fraction of the query matched AND fraction
        # of the symbol's own identity matched), not just query-relative:
        # otherwise a long, verbose name that happens to contain one query
        # word (e.g. test_cache_key_is_stable_and_input_sensitive, testing
        # something named RequestCache) outscores or ties the precise
        # match, because query-relative overlap alone can't tell "this
        # symbol IS what you're asking about" from "this symbol merely
        # mentions it in passing."
        for path, sym in self.graph.all_symbols():
            name_tokens = _tokenize(str(sym["name"]))
            overlap = _overlap(query_tokens, name_tokens)
            if str(sym["name"]).lower() in query.lower() or overlap:
                query_ratio = len(overlap) / max(len(query_tokens), 1)
                name_ratio = len(overlap) / max(len(name_tokens), 1)
                score = 1.0 + query_ratio + name_ratio
                hits.append(
                    RetrievalHit(
                        file=path,
                        symbol=str(sym["name"]),
                        kind=str(sym["kind"]),
                        line=int(sym["start_line"]),
                        score=score,
                        reason="symbol name match",
                    )
                )

        matched_files = {h.file for h in hits}

        # Pass 2: file-path token overlap, for files not already surfaced
        # by a symbol match. This is the fallback for questions about a
        # file/module as a whole rather than a specific symbol.
        for path in self.graph.files:
            if path in matched_files:
                continue
            path_tokens = _tokenize(path)
            overlap = _overlap(query_tokens, path_tokens)
            if overlap:
                query_ratio = len(overlap) / max(len(query_tokens), 1)
                path_ratio = len(overlap) / max(len(path_tokens), 1)
                hits.append(
                    RetrievalHit(
                        file=path,
                        symbol=None,
                        kind=None,
                        line=None,
                        score=0.5 * (query_ratio + path_ratio),
                        reason="file path match",
                    )
                )

        # Pass 3: bounded source-text fallback.  This runs only when the
        # fast metadata passes did not yield two distinct production files.
        # It therefore repairs vocabulary-only misses without making broad
        # source scanning the normal retrieval path or crowding out clear
        # symbol/path evidence.
        surfaced = {h.file for h in hits}
        production_files = {hit.file for hit in hits if not self._is_support_path(hit.file)}
        if len(production_files) < min(2, limit):
            for hit in self._content_hits(query_tokens):
                if hit.file not in surfaced:
                    hits.append(hit)
                    surfaced.add(hit.file)

        # Pass 4: semantic fallback, only for files the lexical/graph/text
        # passes above didn't already surface -- catches the "right file,
        # wrong vocabulary" case token overlap structurally can't.
        if self.vector_store is not None:
            for doc_id, score, _meta in self.vector_store.search(query, limit=limit):
                if doc_id not in surfaced:
                    hits.append(
                        RetrievalHit(
                            file=doc_id,
                            symbol=None,
                            kind=None,
                            line=None,
                            score=score,
                            reason="semantic match",
                        )
                    )
                    surfaced.add(doc_id)

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]
