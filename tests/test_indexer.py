from pathlib import Path

from brainstem.indexer.graph import build_graph
from brainstem.indexer.parser import extract_symbols
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
