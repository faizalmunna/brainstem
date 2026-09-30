from pathlib import Path

import pytest

from brainstem.indexer.graph import build_graph, load_graph, save_graph
from brainstem.indexer.store import export_graph, export_graph_store, load_graph_store, save_graph_store
from brainstem.indexer.parser import extract_imports, extract_symbols
from brainstem.go_enrichment import _go_env
from brainstem.manifest import default_manifest


def test_extract_symbols_python():
    source = b"""
def foo(x):
    return x + 1


class Bar:
    def method(self):
        pass
"""
    symbols = extract_symbols(source, "python")
    names = {s.name for s in symbols}
    assert names == {"foo", "Bar", "method"}
    kinds = {s.name: s.kind for s in symbols}
    assert kinds["foo"] == "function"
    assert kinds["Bar"] == "class"
    assert kinds["method"] == "function"  # method_definition isn't in the python node map; methods parse as function_definition


def test_extract_symbols_unsupported_language_returns_empty():
    assert extract_symbols(b"whatever", "cobol") == []


def test_build_graph_indexes_a_small_repo(tmp_path: Path):
    (tmp_path / "a.py").write_text("def hello():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "c.py").write_text("def skip_me():\n    pass\n", encoding="utf-8")

    manifest = default_manifest("test-repo")
    manifest.index.ignore = manifest.index.ignore + ["ignored"]

    graph = build_graph(tmp_path, manifest)
    stats = graph.stats()

    assert stats["files"] == 2
    assert stats["symbols"] == 2
    names = {sym["name"] for _, sym in graph.all_symbols()}
    assert names == {"hello", "Widget"}


def test_build_graph_incremental_reuses_unchanged_files(tmp_path: Path):
    (tmp_path / "a.py").write_text("def hello():\n    pass\n", encoding="utf-8")
    manifest = default_manifest("test-repo")

    first = build_graph(tmp_path, manifest)
    second = build_graph(tmp_path, manifest, existing=first)

    assert first.files["a.py"] is second.files["a.py"]


def test_build_graph_rejects_an_escaping_source_symlink(tmp_path: Path):
    outside = tmp_path.parent / "outside-sensitive.py"
    outside.write_text("def should_not_be_indexed():\n    pass\n", encoding="utf-8")
    link = tmp_path / "escaped.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this test host")

    graph = build_graph(tmp_path, default_manifest("repo"))

    assert "escaped.py" not in graph.files


def test_build_graph_rejects_binary_and_malformed_utf8_source(tmp_path: Path):
    (tmp_path / "nul.py").write_bytes(b"def nul():\x00\n")
    (tmp_path / "malformed.py").write_bytes(b"def malformed():\n  \xff\n")
    (tmp_path / "valid.py").write_text("def valid():\n    pass\n", encoding="utf-8")

    graph = build_graph(tmp_path, default_manifest("repo"))

    assert set(graph.files) == {"valid.py"}


def test_go_enrichment_does_not_inherit_unsafe_goflags(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GOFLAGS", "-exec=untrusted-wrapper")

    assert _go_env(tmp_path)["GOFLAGS"] == "-mod=readonly"


def test_load_graph_treats_a_corrupt_cache_as_missing_so_reindex_can_recover(tmp_path: Path):
    graph_path = tmp_path / ".brain" / "index" / "graph.json"
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text("{not valid json", encoding="utf-8")

    assert load_graph(graph_path) is None

    (tmp_path / "a.py").write_text("def healthy():\n    pass\n", encoding="utf-8")
    graph = build_graph(tmp_path, default_manifest("test-repo"))
    save_graph(graph, graph_path)

    restored = load_graph(graph_path)
    assert restored is not None
    assert "a.py" in restored.files


def test_build_graph_resolves_python_edges(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "base.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    (tmp_path / "pkg" / "derived.py").write_text(
        "from pkg.base import Base\n\n\nclass Derived(Base):\n    pass\n", encoding="utf-8"
    )

    graph = build_graph(tmp_path, default_manifest("test-repo"))

    assert graph.edges.get("pkg/derived.py") == ["pkg/base.py"]
    assert "pkg/derived.py" in graph.neighbors("pkg/base.py")
    assert "pkg/base.py" in graph.neighbors("pkg/derived.py")


def test_build_graph_resolves_js_relative_edges(tmp_path: Path):
    (tmp_path / "a.js").write_text("export function a() {}\n", encoding="utf-8")
    (tmp_path / "b.js").write_text("import { a } from './a';\n\nfunction b() { a(); }\n", encoding="utf-8")

    graph = build_graph(tmp_path, default_manifest("test-repo"))

    assert graph.edges.get("b.js") == ["a.js"]


def test_build_graph_resolves_relative_python_imports(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "base.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    (tmp_path / "pkg" / "sub").mkdir()
    (tmp_path / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "child.py").write_text(
        "from ..base import Base\nfrom .sibling import Thing\n\n\nclass Child(Base):\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "sub" / "sibling.py").write_text("class Thing:\n    pass\n", encoding="utf-8")

    graph = build_graph(tmp_path, default_manifest("test-repo"))

    assert graph.edges.get("pkg/sub/child.py") == ["pkg/base.py", "pkg/sub/sibling.py"]


def test_build_graph_resolves_bare_relative_python_import_names_and_aliases(tmp_path: Path):
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "base.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "sibling.py").write_text("class Sibling:\n    pass\n", encoding="utf-8")
    (tmp_path / "pkg" / "sub" / "consumer.py").write_text(
        "from . import sibling as local_sibling\nfrom .. import base\n",
        encoding="utf-8",
    )

    graph = build_graph(tmp_path, default_manifest("test-repo"))

    assert graph.edges["pkg/sub/consumer.py"] == ["pkg/base.py", "pkg/sub/sibling.py"]


def test_extract_imports_preserves_concrete_targets_for_bare_relative_imports():
    source = b"from . import sibling, another as local_another\nfrom .. import base\n"

    assert extract_imports(source, "python") == [".sibling", ".another", "..base"]


def test_build_graph_ignores_external_imports(tmp_path: Path):
    (tmp_path / "a.py").write_text("import os\nimport sys\n\ndef f():\n    pass\n", encoding="utf-8")

    graph = build_graph(tmp_path, default_manifest("test-repo"))

    assert graph.edges.get("a.py", []) == []


def test_build_graph_resolves_go_module_import_to_local_package_files(tmp_path: Path):
    (tmp_path / "internal" / "auth").mkdir(parents=True)
    (tmp_path / "go.mod").write_text("module example.com/acme/service\n", encoding="utf-8")
    (tmp_path / "main.go").write_text(
        'package main\n\nimport "example.com/acme/service/internal/auth"\n\nfunc main() { auth.Check() }\n',
        encoding="utf-8",
    )
    (tmp_path / "internal" / "auth" / "auth.go").write_text(
        "package auth\n\nfunc Check() bool { return true }\n", encoding="utf-8"
    )
    (tmp_path / "internal" / "auth" / "auth_test.go").write_text(
        "package auth\n\nfunc TestCheck() {}\n", encoding="utf-8"
    )

    graph = build_graph(tmp_path, default_manifest("go-repo"))

    assert graph.edges["main.go"] == ["internal/auth/auth.go"]


def test_build_graph_resolves_java_package_and_static_member_imports(tmp_path: Path):
    auth = tmp_path / "src" / "main" / "java" / "com" / "acme" / "auth"
    app = tmp_path / "src" / "main" / "java" / "com" / "acme" / "app"
    auth.mkdir(parents=True)
    app.mkdir(parents=True)
    (auth / "AuthService.java").write_text(
        "package com.acme.auth;\npublic class AuthService { public static boolean check() { return true; } }\n",
        encoding="utf-8",
    )
    (app / "Login.java").write_text(
        "package com.acme.app;\nimport static com.acme.auth.AuthService.check;\npublic class Login { boolean run() { return check(); } }\n",
        encoding="utf-8",
    )

    graph = build_graph(tmp_path, default_manifest("java-repo"))

    assert graph.edges["src/main/java/com/acme/app/Login.java"] == ["src/main/java/com/acme/auth/AuthService.java"]


def test_sqlite_graph_store_round_trips_and_bounded_export(tmp_path: Path):
    (tmp_path / "a.py").write_text("from b import value\n\ndef run():\n return value\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value = 1\n", encoding="utf-8")
    graph = build_graph(tmp_path, default_manifest("repo"))

    store_path = tmp_path / ".brain" / "index" / "graph.sqlite"
    save_graph_store(graph, store_path)
    restored = load_graph_store(store_path)

    assert restored is not None
    assert restored.model_dump() == graph.model_dump()
    exported = export_graph(restored, focus_path="a.py", depth=1, max_nodes=1)
    assert exported.schema_version == 1
    assert exported.truncated
    assert [node.path for node in exported.nodes] == ["a.py"]

    # The scalable route reads only the selected neighbourhood from SQLite,
    # rather than materializing the full graph in a host/UI process.
    direct = export_graph_store(store_path, focus_path="a.py", depth=1, max_nodes=1)
    assert direct is not None
    assert [node.path for node in direct.nodes] == [node.path for node in exported.nodes]
    assert direct.truncated is exported.truncated


def test_sqlite_graph_store_bounds_a_high_fanout_neighborhood(tmp_path: Path):
    (tmp_path / "hub.py").write_text("def hub():\n    return 1\n", encoding="utf-8")
    for number in range(10):
        (tmp_path / f"leaf_{number}.py").write_text(
            f"from hub import hub\n\ndef leaf_{number}():\n    return hub()\n", encoding="utf-8"
        )
    graph = build_graph(tmp_path, default_manifest("repo"))
    store_path = tmp_path / ".brain" / "index" / "graph.sqlite"
    save_graph_store(graph, store_path)

    exported = export_graph_store(store_path, focus_path="hub.py", depth=1, max_nodes=3)

    assert exported is not None
    assert exported.truncated
    assert len(exported.nodes) == 3
    assert all(node.path in graph.files for node in exported.nodes)


def test_sqlite_graph_store_preserves_corrupt_state_then_recovers_on_reindex(tmp_path: Path):
    (tmp_path / "healthy.py").write_text("def healthy():\n    return True\n", encoding="utf-8")
    graph = build_graph(tmp_path, default_manifest("repo"))
    store_path = tmp_path / ".brain" / "index" / "graph.sqlite"
    store_path.parent.mkdir(parents=True)
    store_path.write_bytes(b"not a sqlite database")

    save_graph_store(graph, store_path)

    assert load_graph_store(store_path) is not None
    assert list(store_path.parent.glob("graph.corrupt-*.sqlite"))
