# Native acceleration boundary

`brainstem-native` is an optional Rust extension boundary, not a second
implementation of the product. The portable Python engine remains complete
and is selected unless a separately released native wheel reports:

1. the compatible ABI version;
2. verified integrity;
3. graph-output parity with Python; and
4. repeatable performance evidence on Windows, Linux, and macOS.

Assembly and C++ are intentionally absent. They will be considered only for a
measured, isolated bottleneck that Rust cannot address; neither expands MCP
host compatibility.
