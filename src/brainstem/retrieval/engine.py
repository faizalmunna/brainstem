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


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    file: str
    symbol: str | None
    kind: str | None
    line: int | None
    score: float
    reason: str


class RetrievalEngine:
    def __init__(self, graph: RepoGraph, vector_store=None) -> None:
        self.graph = graph
        # Deterministic retrieval works fully with vector_store=None. When
        # available, vectors only add candidates the lexical/graph passes
        # missed; they never replace the explainable base ranking.
        self.vector_store = vector_store

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

        # Pass 3: semantic fallback, only for files the lexical/graph
        # passes above didn't already surface -- catches the "right file,
        # wrong vocabulary" case token overlap structurally can't.
        if self.vector_store is not None:
            surfaced = {h.file for h in hits}
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
