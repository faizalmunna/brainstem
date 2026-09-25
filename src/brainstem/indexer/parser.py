"""Tree-sitter-based symbol extraction.

This is a deterministic code-understanding layer: no LLM calls, no embeddings,
and ground-truth structure straight from the grammar. It uses the
pip-installable `tree-sitter-language-pack` rather
than hand-building grammars from a Rust toolchain, since that toolchain
isn't reliably available in every environment this tool needs to run in;
the node-type maps below are the part that would move into brain-core (Rust)
first if profiling justifies the port.

Coverage is intentionally a starter set, not exhaustive: add a language by
adding an extension mapping and a node-type table, nothing else changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".rs": "rust",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
}

# node type -> symbol kind, per language. The declaration node must expose
# a "name" field per its grammar (true for all listed here).
SYMBOL_NODE_TYPES: dict[str, dict[str, str]] = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "rust": {
        "function_item": "function",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "impl_item": "impl",
    },
    "javascript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_definition": "method",
    },
    "tsx": {
        "function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_definition": "method",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "type",
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "method_declaration": "method",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
    },
    "ruby": {
        "method": "method",
        "class": "class",
        "module": "module",
    },
}


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    kind: str
    start_line: int
    end_line: int


# Node types that introduce an import/use in each language. Resolution of
# the raw string each yields into an actual repo file happens in graph.py,
# since that needs repo-wide file listing, not just single-file parsing.
IMPORT_NODE_TYPES: dict[str, set[str]] = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "tsx": {"import_statement"},
    "rust": {"use_declaration"},
    "go": {"import_declaration"},
    "java": {"import_declaration"},
}


def language_for_path(suffix: str) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(suffix)


def _strip_quotes(text: str) -> str:
    return text.strip().strip("'\"")


def _extract_import_text(node: Node, source: bytes, language: str) -> list[str]:
    if language == "python":
        if node.type == "import_from_statement":
            module = node.child_by_field_name("module_name")
            if module is None:
                return []
            return [source[module.start_byte : module.end_byte].decode("utf-8", errors="replace")]
        # import_statement: one or more dotted_name / aliased_import children
        out = []
        for child in node.named_children:
            if child.type in ("dotted_name", "aliased_import"):
                name_node = child.child_by_field_name("name") if child.type == "aliased_import" else child
                if name_node is not None:
                    out.append(source[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace"))
        return out

    if language in ("javascript", "typescript", "tsx"):
        src = node.child_by_field_name("source")
        if src is None:
            return []
        return [_strip_quotes(source[src.start_byte : src.end_byte].decode("utf-8", errors="replace"))]

    if language == "rust":
        text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        text = text.strip()
        if text.startswith("use "):
            text = text[len("use ") :]
        return [text.rstrip(";").strip()]

    if language == "go":
        # A Go import declaration may contain one quoted import or an import
        # block with aliases. The quoted paths are the stable part needed for
        # intra-repository resolution; aliases do not alter the package path.
        text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        return re.findall(r'"([^"\\]+)"', text)

    if language == "java":
        text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()
        text = re.sub(r"^import\s+(?:static\s+)?", "", text)
        target = text.rstrip(";").strip()
        return [target] if target else []

    return []


def _walk_imports(node: Node, source: bytes, node_types: set[str], language: str, out: list[str]) -> None:
    if node.type in node_types:
        out.extend(_extract_import_text(node, source, language))
        return  # don't descend into an import statement's own children
    for child in node.children:
        _walk_imports(child, source, node_types, language, out)


def extract_imports(source: bytes, language: str) -> list[str]:
    """Return raw import/use targets exactly as written (e.g. "foo.bar",
    "./sibling", "crate::mod::Thing") -- unresolved. See graph.py for
    resolution against the repo's actual file layout. Unsupported
    languages return [] rather than raising."""
    node_types = IMPORT_NODE_TYPES.get(language)
    if node_types is None:
        return []
    try:
        parser = get_parser(language)  # type: ignore[arg-type]
    except LookupError:
        return []
    tree = parser.parse(source)
    raw: list[str] = []
    _walk_imports(tree.root_node, source, node_types, language, raw)
    return raw


def _node_name(node: Node, source: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    return source[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="replace")


def _walk(node: Node, source: bytes, node_types: dict[str, str], out: list[Symbol]) -> None:
    kind = node_types.get(node.type)
    if kind is not None:
        name = _node_name(node, source)
        if name:
            out.append(
                Symbol(
                    name=name,
                    kind=kind,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )
    for child in node.children:
        _walk(child, source, node_types, out)


def extract_symbols(source: bytes, language: str) -> list[Symbol]:
    """Parse `source` and return every declaration matching this language's
    SYMBOL_NODE_TYPES table. Returns [] for unsupported/unparseable input
    rather than raising -- a file with no extractable symbols is still a
    valid, indexable node in the repo graph."""
    node_types = SYMBOL_NODE_TYPES.get(language)
    if node_types is None:
        return []
    try:
        parser = get_parser(language)  # type: ignore[arg-type]
    except LookupError:
        return []

    tree = parser.parse(source)
    symbols: list[Symbol] = []
    _walk(tree.root_node, source, node_types, symbols)
    return symbols
