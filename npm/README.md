# @faizalmunna/brainstem (npm wrapper)

This is an **installer/launcher for the real Python implementation** of
brainstem — a portable AI engineering brain (repo intelligence, memory,
skills) exposed over MCP to any coding agent. It is not a Node
reimplementation; every command runs the actual Python CLI in a private
virtual environment this package sets up for itself on install.

## Requirements

- Node.js 18+ (to run this wrapper)
- [uv](https://docs.astral.sh/uv/) on `PATH` (to install the actual tool).
  The wrapper uses the reviewed `uv.lock` shipped in the package, so a normal
  install has one reproducible dependency graph. `uv` can provision Python
  3.11 when needed.

Nothing is installed to your system/global Python — the wrapper creates
its own private `.venv` inside this package's own install directory.
When `uv` is available, it installs the dependency graph pinned in the
package's reviewed lockfile. A legacy `pip` fallback exists only when
`BRAINSTEM_ALLOW_UNVERIFIED_PIP=1` is explicitly set; it is not suitable for
production or enterprise deployment because pip resolves the loose project
constraints instead of the lockfile.

## Install

```bash
npm install -g @faizalmunna/brainstem
```

## Use

Identical to the Python CLI:

```bash
brainstem init --path /path/to/some/repo
brainstem index --path /path/to/some/repo
brainstem query "where is authentication handled?" --path /path/to/some/repo
brainstem skills --packs --path /path/to/some/repo
brainstem serve --path /path/to/some/repo --profile readonly
```

## Why an npm wrapper for a Python tool?

So `npx @faizalmunna/brainstem` / `npm install -g @faizalmunna/brainstem` works for people whose
default toolchain is the Node/JS ecosystem, without needing them to know
this is written in Python first. If you're working from a source checkout,
`uv sync` followed by `uv run brainstem` skips the wrapper layer entirely.

## License

MIT.

## Project links

- Source and issues: https://github.com/faizalmunna/brainstem
- Security reports: https://github.com/faizalmunna/brainstem/security/advisories/new
