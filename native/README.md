# Native components

The portable Python engine is the authority for Brainstem's graph, parser,
MCP contract, permissions, and workflow state. These components accelerate or
validate narrow, independently testable work without changing those contracts.

| Component | Responsibility | Safety boundary |
| --- | --- | --- |
| `brainstem-native` (Rust) | Parallel batch reading and SHA-256 fingerprinting of source files | Python's walker selects every path; Python re-verifies every digest before it becomes graph evidence. |
| C++ UTF-8 validator | Strict UTF-8 validation of Rust-read bytes | C ABI only; invalid input is excluded and Python remains the fallback. |
| x86-64 assembly | Linux-only NUL-byte scan inside the native reader | One small System V ABI routine; all other targets use the C++ fallback. |
| `brainstem-goanalyzer` (Go) | Offline Go-AST import extraction from explicit file paths | Reads JSON on stdin, performs no module resolution, network access, or project execution. |

Build checks run in CI:

```bash
cargo test --manifest-path native/brainstem-native/Cargo.toml
(cd native/brainstem-goanalyzer && go test ./...)
```

The Rust extension deliberately reports that it is **not** a complete native
graph engine. It is optional, and Python continues to index safely when no
native wheel is installed or native output is malformed.
