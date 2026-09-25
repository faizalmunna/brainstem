from brainstem.indexer.graph import build_graph
from brainstem.manifest import default_manifest
from brainstem.retrieval.context import MAX_BUNDLE_CHARS, build_context_bundle
from brainstem.retrieval.engine import RetrievalEngine, RetrievalHit, _tokenize


def test_tokenize_splits_camel_case():
    assert _tokenize("RequestCache") == {"request", "cache"}
    assert _tokenize("HTTPServer") == {"http", "server"}
    assert _tokenize("cache_key") == {"cache", "key"}


def test_tokenize_filters_stopwords_only_when_asked():
    assert _tokenize("how is the cache implemented") == {
        "how", "is", "the", "cache", "implemented",
    }
    assert _tokenize("how is the cache implemented", filter_stopwords=True) == {
        "cache", "implemented",
    }


def _build(tmp_path, files: dict[str, str]):
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return build_graph(tmp_path, default_manifest("test-repo"))


def test_precise_symbol_match_outranks_incidental_mention_in_a_test_name(tmp_path):
    graph = _build(
        tmp_path,
        {
            "cache.py": "class RequestCache:\n    pass\n",
            "test_cache.py": (
                "def test_cache_key_is_stable_and_survives_a_round_trip_through_storage():\n"
                "    pass\n"
            ),
        },
    )
    engine = RetrievalEngine(graph)
    hits = engine.retrieve("where is the request cache implemented", limit=5)

    assert hits, "expected at least one hit"
    assert hits[0].file == "cache.py"
    assert hits[0].symbol == "RequestCache"


def test_retrieve_falls_back_to_path_match_when_no_symbol_matches(tmp_path):
    graph = _build(tmp_path, {"widgets/renderer.py": "x = 1\n"})  # no extractable symbols
    engine = RetrievalEngine(graph)
    hits = engine.retrieve("widget renderer", limit=5)

    assert any(h.file == "widgets/renderer.py" and h.reason == "file path match" for h in hits)


def test_retrieve_empty_query_returns_nothing(tmp_path):
    graph = _build(tmp_path, {"a.py": "def f(): pass\n"})
    engine = RetrievalEngine(graph)
    assert engine.retrieve("   ", limit=5) == []


def test_retrieve_matches_plural_query_against_singular_symbol_name(tmp_path):
    graph = _build(
        tmp_path,
        {"permissions.py": "class Permission:\n    pass\n\n\ndef require_permission(x):\n    pass\n"},
    )
    engine = RetrievalEngine(graph)
    hits = engine.retrieve("how are permissions enforced", limit=5)

    assert any(h.file == "permissions.py" for h in hits)


def test_retrieve_matches_past_tense_question_to_silent_e_symbol(tmp_path):
    graph = _build(
        tmp_path,
        {
            "indexer/graph.py": "def _resolve_python(raw):\n    return raw\n",
            "tests/test_graph.py": (
                "def test_relative_python_imports_are_handled():\n    pass\n"
            ),
        },
    )
    engine = RetrievalEngine(graph)

    hits = engine.retrieve("where are relative python imports resolved to file paths", limit=1)

    assert hits[0].file == "indexer/graph.py"
    assert hits[0].symbol == "_resolve_python"


def test_retrieve_surfaces_dependency_neighbors_for_a_known_file(tmp_path):
    graph = _build(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/base.py": "class Base:\n    pass\n",
            "pkg/derived.py": "from pkg.base import Base\n\n\nclass Derived(Base):\n    pass\n",
        },
    )
    engine = RetrievalEngine(graph)
    hits = engine.retrieve("pkg/derived.py", limit=10)

    assert any(h.file == "pkg/base.py" and "dependency neighbor" in h.reason for h in hits)


def test_context_bundle_returns_line_numbered_excerpt_around_hit(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("first\nsecond\ndef target():\n    return 42\nfifth\n", encoding="utf-8")
    hit = RetrievalHit("service.py", "target", "function", 3, 1.0, "symbol name match")

    bundle = build_context_bundle(tmp_path, [hit], max_chars=500, context_lines=1)

    assert bundle["total_chars"] > 0
    assert bundle["excerpts"][0]["start_line"] == 2
    assert bundle["excerpts"][0]["end_line"] == 4
    assert "    3: def target():" in bundle["excerpts"][0]["content"]


def test_context_bundle_refuses_paths_outside_repository(tmp_path):
    outside = tmp_path.parent / "outside-secret.py"
    outside.write_text("DO_NOT_EXPOSE", encoding="utf-8")
    hit = RetrievalHit("../outside-secret.py", None, None, 1, 1.0, "unsafe test")

    bundle = build_context_bundle(tmp_path, [hit], max_chars=500)

    assert bundle["excerpts"] == []
    assert bundle["skipped"] == 1


def test_context_bundle_enforces_global_response_cap(tmp_path):
    source = tmp_path / "large.py"
    source.write_text("x" * 20_000, encoding="utf-8")
    hit = RetrievalHit("large.py", None, None, 1, 1.0, "large file")

    bundle = build_context_bundle(tmp_path, [hit], max_chars=MAX_BUNDLE_CHARS)

    assert bundle["total_chars"] <= MAX_BUNDLE_CHARS
    assert bundle["truncated"] is True


def test_context_bundle_skips_likely_credential_files(tmp_path):
    credential = tmp_path / ".env"
    credential.write_text("API_KEY=not-for-context", encoding="utf-8")
    hit = RetrievalHit(".env", None, None, 1, 1.0, "unsafe test")

    bundle = build_context_bundle(tmp_path, [hit], max_chars=500)

    assert bundle["excerpts"] == []
    assert bundle["sensitive_skipped"] == 1


def test_context_bundle_deduplicates_overlapping_symbol_excerpts(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("\n".join(f"line {i}" for i in range(1, 30)), encoding="utf-8")
    hits = [
        RetrievalHit("service.py", "first", "function", 10, 1.0, "symbol name match"),
        RetrievalHit("service.py", "second", "function", 11, 0.9, "symbol name match"),
        RetrievalHit("service.py", "distant", "function", 25, 0.8, "symbol name match"),
    ]

    bundle = build_context_bundle(tmp_path, hits, max_chars=2_000, context_lines=2)

    assert [excerpt["symbol"] for excerpt in bundle["excerpts"]] == ["first", "distant"]
    assert bundle["deduplicated"] == 1
