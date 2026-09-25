# Brainstem

> Give coding agents the relevant map of a repository—not the whole repository.

Brainstem is a local, model-neutral repository-intelligence layer for coding
agents. It indexes a project, retrieves the smallest relevant source slice,
and serves bounded, permission-scoped evidence through MCP.

It works beside your preferred agent and editor. Brainstem does not choose a
model, host a remote service, or replace your coding workflow; it makes the
context supplied to that workflow more focused, current, and auditable.

```
Coding agent / IDE / CLI
          │  local stdio MCP
          ▼
┌────────────────────────────────────────────────────┐
│ Brainstem                                            │
│ repository graph → focused retrieval → task packet   │
│ local memory → workflow evidence → permission gates  │
└────────────────────────────────────────────────────┘
          │
          ▼
Target repository + local .brain/ state
```

## What it provides

- **Focused repository context** — indexes symbols and dependency edges for
  Python, JavaScript, TypeScript, Rust, Go, and Java.
- **Bounded task packets** — `prepare` combines relevant source, likely tests,
  repository rules, current Git signals, risk flags, and fresh local memory
  under a hard whole-packet size limit.
- **Local durable memory** — decisions and incidents can be attached to source
  references; entries tied to changed source are excluded as stale.
- **Explicit security boundaries** — local stdio MCP, a read-only default
  profile, least-privilege capability grants, and denied-action audit records.
- **Workflow evidence** — design, plan, test, verification, and review
  artifacts are durable; the connected host still performs the work.
- **Reusable skills** — bundled engineering guidance plus per-repository skill
  controls.

## Install from source

Brainstem is currently distributed from source. It requires Python 3.11+ and
[uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
```

Index a project and compile evidence for a task:

```bash
uv run brainstem init --path /path/to/your-project
uv run brainstem index --path /path/to/your-project
uv run brainstem prepare "trace the login redirect bug" --path /path/to/your-project
```

Start every coding or review task with `prepare`. Expand context only when the
packet identifies a specific missing symbol, dependency, or test.

## Measure retrieval locally

`evaluate` scores Brainstem against labelled tasks that you keep locally. A
case file contains a task description and expected repository-relative files;
it is never uploaded. The report includes Recall@k, first relevant rank, exact
compact packet characters, and the packet's context-character reduction versus
the indexed source corpus. It does **not** claim provider token counts.

```json
{
  "format_version": 1,
  "cases": [
    {
      "id": "login-validation",
      "query": "trace login token validation",
      "required_files": ["src/auth/tokens.py", "tests/test_tokens.py"]
    }
  ]
}
```

```bash
uv run brainstem evaluate --path /path/to/your-project --cases /path/to/cases.json
```

Use a reviewed, representative suite before comparing configurations. Keep
private task descriptions and results outside a public repository.

## Connect an MCP host

Brainstem writes no editor settings by itself. It prints a configuration for
you to review and paste into an MCP-capable host:

```bash
uv run brainstem host config generic --path /path/to/your-project --profile readonly
uv run brainstem host connect-prompt --path /path/to/your-project --profile readonly
```

The portable `generic` option emits a local stdio `mcpServers` entry. Supported
host-specific formats include Codex, Claude Code, Cursor, VS Code, and Gemini.
Without an explicitly selected profile, Brainstem exposes only read-only
repository intelligence.

## Docker

The Docker image builds the locked runtime dependency graph and runs as an
unprivileged user:

```bash
docker build --tag brainstem:local .
docker run --rm brainstem:local --help
```

To index a project, mount only that project. Indexing writes its local `.brain`
state, so the mount must be writable:

```bash
# PowerShell
docker run --rm -it -v "${PWD}:/workspace" brainstem:local init --path /workspace
docker run --rm -it -v "${PWD}:/workspace" brainstem:local index --path /workspace

# bash/zsh: preserve ownership of generated files on Linux/macOS
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD:/workspace" brainstem:local index --path /workspace
```

For an MCP integration, set the host's local command to `docker run --rm -i
... brainstem:local serve --path /workspace`. Docker is a CLI runtime, not a
network service.

## Security model

- Brainstem uses local stdio MCP; it does not expose repository content through
  an HTTP server.
- The default profile is read-only. Writes and verification need an explicit
  capability grant at the MCP tool boundary.
- Sensitive paths are excluded from task source bundles, and index freshness
  is included so stale context is not presented as current.
- High-risk verification can opt into a fail-closed, digest-pinned Docker
  runner with no network, a read-only source mount, a non-root user, dropped
  capabilities, `no-new-privileges`, and resource limits.

See [SECURITY.md](SECURITY.md) for the reporting policy and release controls.

## Distribution status

| Path | Status |
| --- | --- |
| Source + `uv` | Available now |
| Docker image | Build locally from this repository |
| npm wrapper | Pack/install is tested locally; public publishing is an explicit future maintainer decision |
| PyPI | Not published |

The npm package is an installer for this Python implementation, not a separate
Node rewrite. Its source is in [`npm/`](npm/).

## Verification

```bash
uv lock --check
uv run pytest
uv run brainstem release check --path .
```

The production gate is intentionally fail-closed: it requires matching public
repository metadata, a real security reporting channel, a clean worktree, and
configured supply-chain controls before a release is marked ready. A `v*` tag
first passes the security, Windows/Linux/macOS, npm-install, and Docker checks;
the Docker lane covers the full x86_64 suite plus portability-critical and npm
checks on Linux ARM64. Only then are release artifacts built and attested. It
never publishes anything automatically.

## License

MIT — see [LICENSE](LICENSE).
