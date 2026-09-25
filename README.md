<p align="center">
  <img src="assets/brainstem-map.svg" alt="Brainstem turns a repository map into bounded local evidence for coding agents" width="100%" />
</p>

<h1 align="center">Brainstem</h1>

<p align="center"><strong>Give your coding agent the relevant map of a repository—not the whole repository.</strong></p>

<p align="center">
  <a href="https://github.com/faizalmunna/brainstem/actions/workflows/ci.yml"><img src="https://github.com/faizalmunna/brainstem/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <a href="https://github.com/faizalmunna/brainstem/actions/workflows/codeql.yml"><img src="https://github.com/faizalmunna/brainstem/actions/workflows/codeql.yml/badge.svg" alt="CodeQL status" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-34d399.svg" alt="MIT license" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-60a5fa.svg" alt="Python 3.11 or newer" />
  <img src="https://img.shields.io/badge/MCP-local%20stdio-a78bfa.svg" alt="Local stdio MCP" />
  <img src="https://img.shields.io/badge/default-read--only-fbbf24.svg" alt="Read-only by default" />
</p>

Brainstem is a local, model-neutral repository-intelligence layer for coding
agents. It indexes a project, retrieves the smallest relevant source slice,
and serves bounded, permission-scoped evidence through MCP. It does not choose
your model, host a remote Brainstem service, or replace your workflow—it makes
the context reaching that workflow more focused, current, and auditable.

| Local-first | Model-neutral | Evidence-bound |
| --- | --- | --- |
| Repository source stays on the machine running Brainstem. | Connect the coding host you already use. | Context, freshness, permissions, and verification are explicit. |

## Why teams use it

<table>
  <tr>
    <td width="33%"><strong>🧠 Understand a real codebase</strong><br/>Build a symbol and dependency graph across Python, JavaScript, TypeScript, Rust, Go, and Java—then retrieve the source, tests, rules, and history that a task actually needs.</td>
    <td width="33%"><strong>✂️ Spend context on evidence</strong><br/>Send bounded task packets instead of repeatedly dumping a repository into a model context window. Expand only for a named missing dependency, symbol, or test.</td>
    <td width="33%"><strong>🛡️ Keep control at the boundary</strong><br/>Local stdio transport, read-only by default, explicit capability grants, sensitive-path exclusions, stale-memory detection, and denied-action audit records.</td>
  </tr>
  <tr>
    <td><strong>🧭 Preserve engineering intent</strong><br/>Durable decisions, incidents, task state, design, plan, test, verification, and review artifacts survive across sessions without pretending stale context is current.</td>
    <td><strong>🧪 Make quality measurable</strong><br/>Evaluate retrieval against private, labelled tasks. See Recall@k, first relevant rank, packet size, and context reduction for your own repositories.</td>
    <td><strong>📚 Bring practical guidance</strong><br/>994 packed engineering playbooks plus four core workflow and repository guides are searchable alongside project-specific skills.</td>
  </tr>
</table>

## Works with the agent you already chose

Brainstem provides reviewed, copy/paste configuration formats for these local
MCP hosts:

| ⚡ Codex | ✦ Claude Code | ◼ Cursor | ⌘ VS Code | ✧ Gemini |
| --- | --- | --- | --- | --- |
| `.codex/config.toml` | `claude mcp add-json` | `.cursor/mcp.json` | `.vscode/mcp.json` | `.gemini/settings.json` |

Any other MCP-capable host can use the portable `mcpServers` definition or the
generated connection prompt. Brainstem stays host-neutral: it supplies
repository evidence; your chosen agent performs the reasoning and changes.

```bash
# Print a host-specific, reviewable local configuration.
uv run brainstem host config codex --path /path/to/your-project --profile readonly

# Or emit a portable local-stdio MCP definition for another host.
uv run brainstem host config generic --path /path/to/your-project --profile readonly
```

## Context savings without guesswork

The goal is not to claim a magic token percentage. It is to remove repeated,
irrelevant repository context while retaining the evidence needed to do the
work safely.

For every labelled task, `evaluate` reports the exact compact-packet character
count, the indexed-source character count, Recall@k, first relevant rank, and
the measured context reduction:

```text
context reduction = 1 − (task packet characters / indexed source characters)
```

This is intentionally provider-neutral—Brainstem does not convert characters
into guessed OpenAI, Anthropic, or other provider token counts. Savings vary by
task and repository size. For a tiny repository, sending the whole safe source
set can be shorter than a richly structured packet; `--context-mode auto`
chooses the smaller safe option rather than manufacturing a saving claim.

```bash
uv run brainstem evaluate --path /path/to/your-project --cases /path/to/cases.json
```

## A practical workflow

```bash
# 1. Create local Brainstem state and index the repository.
uv run brainstem init --path /path/to/your-project
uv run brainstem index --path /path/to/your-project

# 2. Start a task with bounded, fresh evidence.
uv run brainstem prepare "trace the login redirect bug" --path /path/to/your-project

# 3. Let the connected host use that packet before opening more files.
uv run brainstem serve --path /path/to/your-project --profile readonly
```

`prepare` combines relevant source, likely tests, repository rules, current Git
signals, risk flags, and fresh local memory under a hard whole-packet size
limit. When symbols and paths produce too little production evidence, it can
make one bounded, local-only source-text pass: at most 500 files, 2 MB total,
and 256 KB per file. It skips sensitive filenames, writes no source terms to
the index, and still returns only capped excerpts.

## Enterprise-ready controls, without model lock-in

| Need | Brainstem control |
| --- | --- |
| Keep source off a hosted intermediary | Local filesystem state and local stdio MCP; no Brainstem HTTP service by default. |
| Limit what an agent can do | Read-only default profile; explicit grants at the MCP boundary for writes and verification. |
| Avoid stale or untraceable advice | Source-linked memory is freshness-checked; workflow artifacts retain design, test, verification, and review evidence. |
| Verify high-risk changes defensibly | Optional fail-closed Docker runner requires a digest-pinned image and uses a read-only source mount, no network, non-root user, dropped capabilities, `no-new-privileges`, and resource limits. |
| Standardize quality across different agents | Host-neutral context packets, reusable project skills, and local evaluation instead of one vendor-specific workflow. |

Brainstem is not a claim of compliance certification and does not replace an
organization's access controls, review policy, or secure-development program.
It is the local intelligence and control layer those processes can build on.

## Real technology, visible controls

| Layer | Technology in this repository |
| --- | --- |
| Runtime | Python 3.11+, Typer, Pydantic, Tree-sitter language packs, FastMCP, PathSpec, PyYAML, HTTPX, Watchfiles |
| Optional retrieval | LanceDB and FastEmbed, with deterministic lexical retrieval available without an embedding dependency |
| Distribution | `uv`-locked Python dependency graph, Node.js 18+ installer wrapper, Docker runtime |
| Release integrity | Windows, Linux, and macOS CI; npm-install and Docker x86_64/ARM64 smoke coverage; SBOM generation; CodeQL; Dependabot; secret scanning and push protection |
| GitHub delivery | Protected `main`, pull-request review, up-to-date required checks, force-push/deletion blocking, and GitHub private vulnerability reporting |

## Install and run

Brainstem is available from source today and requires Python 3.11+ and
[uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/faizalmunna/brainstem.git
cd brainstem
uv sync --extra dev
uv run brainstem --help
```

The npm wrapper is an installer for this Python implementation—not a separate
Node rewrite. Its public release remains intentionally unpublished until its
maintainer completes npm registry authentication. PyPI is also not published.

## Docker

The Docker image builds the locked runtime dependency graph and runs as an
unprivileged user:

```bash
docker build --tag brainstem:local .
docker run --rm brainstem:local --help
```

To index a project, mount only that project. Indexing writes local `.brain/`
state, so the project mount must be writable:

```bash
# PowerShell
docker run --rm -it -v "${PWD}:/workspace" brainstem:local init --path /workspace
docker run --rm -it -v "${PWD}:/workspace" brainstem:local index --path /workspace

# bash/zsh: preserve ownership of generated files on Linux/macOS
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD:/workspace" brainstem:local index --path /workspace
```

## Verify before trusting

```bash
uv lock --check
uv run pytest
uv run brainstem release check --path .
```

The release gate fails closed when repository identity, a security reporting
channel, dependency locking, and supply-chain controls are absent. Version tags
wait for the security, Windows/Linux/macOS, npm-install, and Docker checks
before release artifacts are built and attested; publication remains an
explicit maintainer action.

## Security and contribution boundaries

- Security reports: [private GitHub vulnerability reporting](https://github.com/faizalmunna/brainstem/security/advisories/new)
- Source and issues: [github.com/faizalmunna/brainstem](https://github.com/faizalmunna/brainstem)
- Public repository content intentionally excludes private development notes,
  local plans, transcripts, credentials, and evaluation cases.

See [SECURITY.md](SECURITY.md) for reporting and release controls.

## License

[MIT](LICENSE)
