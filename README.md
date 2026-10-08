<!-- brainstem-readme-facts: mcp_tools=28; bundled_skills=997; skill_packs=92; hosts=9 -->
<!-- brainstem-readme-hosts: generic,codex,claude-code,cursor,vscode,gemini,copilot-cli,opencode,qwen-code -->

<p align="center">
  <img src="assets/brainstem-control-plane.png" alt="A local repository flows into Brainstem's illuminated evidence graph, which safely connects several independent coding agents." width="100%" />
</p>

<h1 align="center">Brainstem</h1>

<p align="center">
  <strong>Local repository intelligence for independent coding agents.</strong><br />
  <sub>Map the codebase once. Give every agent only the evidence, permissions, and next work item it needs.</sub>
</p>

<p align="center">
  <a href="https://github.com/faizalmunna/brainstem/actions/workflows/ci.yml"><img src="https://github.com/faizalmunna/brainstem/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <a href="https://github.com/faizalmunna/brainstem/actions/workflows/codeql.yml"><img src="https://github.com/faizalmunna/brainstem/actions/workflows/codeql.yml/badge.svg" alt="CodeQL status" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-7c3aed?style=flat-square" alt="MIT license" /></a>
  <img src="https://img.shields.io/badge/MCP-local%20stdio-0ea5e9?style=flat-square" alt="Local stdio MCP" />
  <img src="https://img.shields.io/badge/default-read--only-16a34a?style=flat-square" alt="Read only by default" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11 or later" />
  <img src="https://img.shields.io/badge/FastMCP-local%20tool%20surface-7c3aed?style=for-the-badge" alt="FastMCP" />
  <img src="https://img.shields.io/badge/Tree--sitter-code%20parsing-111827?style=for-the-badge" alt="Tree-sitter" />
  <img src="https://img.shields.io/badge/SQLite-transactional%20graph-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/uv-locked%20runtime-DE5FE9?style=for-the-badge&logo=astral&logoColor=white" alt="uv" />
  <img src="https://img.shields.io/badge/Docker-non--root%20runtime-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Node.js-npm%20launcher-339933?style=for-the-badge&logo=nodedotjs&logoColor=white" alt="Node.js npm launcher" />
  <img src="https://img.shields.io/badge/Agent_Plugins-portable%20skills-10A37F?style=for-the-badge" alt="Portable Agent Plugins skills" />
  <img src="https://img.shields.io/badge/GitHub_Actions-verified%20releases-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</p>

> Brainstem is the local control plane between a serious codebase and the coding agents you choose. It creates a repository map, retrieves bounded evidence, preserves decisions, defines permissioned agent roles, and keeps workflow completion tied to verification.

## What changes with Brainstem

| Before | With Brainstem |
| --- | --- |
| Every new agent reloads broad files and guesses at dependencies. | An agent asks for a bounded task packet backed by a local code and dependency graph. |
| Plans, reviewer notes, and test results disappear into chat history. | Decisions, workflow artifacts, and executed verification live in local project state. |
| Powerful tools quietly expand an agent's authority. | Each profile has explicit `READ`, `WRITE`, `EXECUTE`, `NETWORK`, `INSTALL`, `DATABASE`, `DEPLOY`, `DELETE`, and `SECRET` grants. |

<table>
  <tr>
    <td align="center" width="25%"><h2>96.2%</h2><sub>smaller bounded source-context baseline<sup>†</sup></sub></td>
    <td align="center" width="25%"><h2>0.95</h2><sub>Recall@5 0.95 on labelled navigation tasks<sup>†</sup></sub></td>
    <td align="center" width="25%"><h2>997</h2><sub>targeted engineering skills</sub></td>
    <td align="center" width="25%"><h2>28</h2><sub>permission-gated MCP tools</sub></td>
  </tr>
</table>

<sup>†</sup> `60,114 → 2,272` average GPT-4o-tokenized source-context input across 10 labelled questions, measured 2026-09-25 on this repository. This is a measured Brainstem-repository navigation baseline, not a universal claim about every codebase, model bill, or agent outcome. Run `brainstem evaluate` on your own labelled tasks to measure your repository.

## The local intelligence loop

```text
repository ──index──> local graph + SQLite store ──prepare_task──> bounded evidence packet
     ▲                                                                    │
     └──── verified changes, decisions, and workflow evidence ◀──────────┘
                                                                          │
                  independent agent profiles over local stdio MCP ◀──────┘
```

The Python engine is complete and portable: no hosted Brainstem service, cloud account, compiler, or database server is required. State stays in the repository's local `.brain/` directory.

### Provider policy and token discipline

Brainstem can route an optional completion through Anthropic, OpenAI, or a local Ollama model, but provider calls remain outside the deterministic MCP tool surface. The broker obeys `brain.toml` policy, rejects over-budget input before it leaves the machine, sends each provider a native output cap, keys cached answers by the generation cap, and records only aggregate counts locally—never prompts, responses, cache keys, or credentials.

```bash
# Install only the optional cloud-provider SDKs you intend to use.
uv sync --extra providers

# Use the repository policy, or choose a provider/model deliberately.
uv run brainstem ask "Summarize the selected evidence" --path /path/to/repository
uv run brainstem ask "Summarize the selected evidence" --provider ollama --model llama3.2 --max-output-tokens 400 --path /path/to/repository

# Audit cache efficiency and estimated usage. This output has no prompt text.
uv run brainstem usage --path /path/to/repository
```

Token figures are portable character-based estimates for guardrails and trends, not provider billing records. Use provider usage reporting for invoice reconciliation.

## Independent agent team

Brainstem does not pretend that a list of guides is a team. It stores named profiles, declarative teams, responsibilities, permissions, workflow state, and evidence so your connected host can run independent agents with clear boundaries.

| Agent | Owns | Starts with | Cannot bypass |
| --- | --- | --- | --- |
| **Explorer** | Repository map and focused evidence | Read-only task packet | Source and context boundaries |
| **Designer** | Architecture choices and trade-offs | Current rules and dependencies | Required design artifact |
| **Planner** | Small, testable work items | Approved design | Plan evidence before implementation |
| **Implementer** | One bounded change | Plan, context, and grants | Re-verification after change |
| **Tester** | Executed checks and failure evidence | Configured verification commands | A passing self-assessment is not evidence |
| **Reviewer** | Independent approval or return | Plan plus executed evidence | High-risk review independence |
| **Coordinator** | The next ready work item | Workflow state and team contract | Silent agent spawning or privilege expansion |

Brainstem provides the contract; Codex, Claude Code, Cursor, OpenCode, or another host performs the actual model calls and any subagent execution. That keeps the control plane model-neutral and auditable.

```bash
# Create the repository state, then map it.
uv run brainstem init --path /path/to/repository
uv run brainstem index --path /path/to/repository

# Make evidence available to a task before an agent starts coding.
uv run brainstem prepare "trace the login redirect bug" --path /path/to/repository

# Define a least-privilege worker and a team explicitly.
uv run brainstem agent create explorer --permissions READ --path /path/to/repository
uv run brainstem team create delivery --member explorer:explorer --path /path/to/repository

# Or preview then create the complete seven-role, least-privilege delivery team.
uv run brainstem team bootstrap --path /path/to/repository
uv run brainstem team bootstrap --path /path/to/repository --apply
uv run brainstem workflow start "Fix the OAuth callback" --team delivery --path /path/to/repository
```

## Bring your agent, IDE, or CLI

Every integration is a local-stdio MCP configuration, previewed before Brainstem changes anything. A new connection receives the `readonly` profile until you create and select a more capable profile.

| Host | Configuration route | Status |
| --- | --- | --- |
| OpenAI Codex | `~/.codex/config.toml` | User-scoped, native adapter |
| Claude Code | `claude mcp add-json` | Project-scoped adapter |
| Cursor | `.cursor/mcp.json` | Project-scoped adapter |
| VS Code | `.vscode/mcp.json` | Project-scoped adapter |
| Gemini CLI | `.gemini/settings.json` | Project-scoped adapter |
| GitHub Copilot CLI | `~/.copilot/mcp-config.json` | User-scoped adapter |
| OpenCode | `opencode.json` | Project-scoped local-MCP adapter |
| Qwen Code | `.qwen/settings.json` | Project-scoped adapter |
| Any MCP host | Portable `mcpServers` JSON | Copy/paste contract |

```bash
# Inspect only; this never writes host configuration.
uv run brainstem host list
uv run brainstem host config opencode --path /path/to/repository

# Preview, then explicitly apply exactly one entry.
uv run brainstem host install qwen-code --path /path/to/repository
uv run brainstem host install qwen-code --path /path/to/repository --apply

# Verify the selected host configuration and the local MCP handshake.
uv run brainstem host doctor qwen-code --scope project --path /path/to/repository
```

### Native workflow packages

MCP is the live, permission-gated tool connection. A workflow package is
different: it teaches a host how to use the connection and durable evidence
without silently adding a server, hook, credential, or extra permission.
Brainstem ships one tracked portable skill bundle plus small host manifests;
all manifests point at the same reviewed skills rather than copying workflow
text between clients.

| Harness | Package surface | What it adds | Connection remains |
| --- | --- | --- | --- |
| Codex / ChatGPT | Portable Agent Plugin + Codex compatibility manifest | Setup and evidence-gated workflow skills | Explicit local MCP configuration |
| Claude Code | Claude plugin manifest | Shared workflow skills | `brainstem host install claude-code` |
| Cursor | Cursor plugin manifest | Shared workflow skills | `brainstem host install cursor` |
| Kimi Code | Kimi plugin manifest | Shared skills plus the safe setup skill at session start | Its own MCP configuration |
| Pi | Dependency-free Pi package | Shared evidence/workflow skill | Pi's own MCP-extension configuration |
| VS Code, Gemini CLI, Copilot CLI, OpenCode, Qwen Code, generic MCP | Standard local-stdio MCP adapter | Brainstem's 28 permission-gated tools | `brainstem host install <host>` or portable JSON |

The source package is [`plugins/brainstem/`](plugins/brainstem/). Its Codex
marketplace entry is tracked in [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json),
so a checkout can be added as a local marketplace without hand-writing plugin
metadata. The plugin intentionally contains no MCP server, lifecycle hook, or
credential: choose and install the local Brainstem connection separately.

For Codex, add this checkout (or the GitHub repository) as a marketplace, then
enable the `brainstem` package in a trusted project:

```bash
codex plugin marketplace add https://github.com/faizalmunna/brainstem.git
```

For the other harnesses, install the matching package using that host's plugin
manager, then use the MCP command in the table above. Each package is
contract-tested in this repository; host release versions remain responsible
for accepting their published manifest format.

### Native harness package: Pi

Pi uses installable skill packages rather than treating every integration as an
MCP server. Brainstem therefore ships a dependency-free Pi package that teaches
Pi to request bounded evidence, use the durable workflow, and require executed
verification. It does not install a remote tool, add a credential, or claim
that Pi is a native Brainstem MCP client.

```bash
# From a Brainstem checkout. Review the small package before installing it.
pi install ./integrations/pi
```

Pi remains responsible for its own tool and MCP-extension configuration;
Brainstem remains the local evidence and workflow control plane.

### Compose trusted third-party MCP servers

Brainstem can catalog a reviewed peer MCP server beside its own server definition. A descriptor contains only transport metadata and environment-variable *names*. It cannot contain a credential, execute the third-party command, probe the remote URL, or silently modify a host configuration. That preserves the boundary between a local control plane and tools that may have network or write authority.

`brainstem mcp render` emits a generic `mcpServers` entry. Remote-MCP schemas still differ by host, so review and adapt that entry to the selected host's documented remote transport format before installing it.

```json
{
  "name": "github",
  "transport": "streamable-http",
  "url": "https://mcp.example.com/github",
  "env_from": {"Authorization": "GITHUB_TOKEN"},
  "description": "Reviewed GitHub MCP service"
}
```

```bash
# Inspect is data-only. Register requires an explicit write, then render a
# portable entry for the host configuration you have reviewed.
uv run brainstem mcp inspect github-mcp.json
uv run brainstem mcp register github-mcp.json --path /path/to/repository
uv run brainstem mcp register github-mcp.json --path /path/to/repository --apply
uv run brainstem mcp render github --path /path/to/repository
```

## Performance: measured, portable, and honest

| Technology | Role in Brainstem | Status |
| --- | --- | --- |
| **Python** | Complete portable engine and MCP contract | Production |
| **Tree-sitter** | Multi-language repository parsing | Production |
| **SQLite** | Transactional local graph store | Production |
| **Go** | Opt-in, network-disabled Go build/semantic enrichment | Production adapter |
| **Rust** | Optional parallel source ingest and SHA-256 fingerprinting | Buildable source; Python remains the graph authority |
| **C++** | Strict UTF-8 validation inside the Rust ingest module | Buildable source; activated only through the optional native wheel |
| **Assembly** | Linux x86-64 NUL-byte scan with portable fallback | One isolated routine; never used to broaden capability or permissions |

Assembly does not increase host compatibility. New clients come from standard MCP support, documented adapters, safe configuration handling, and contract tests. Native code is only justified after profiling shows a real bottleneck.

```bash
# Create a deterministic benchmark corpus outside the tracked source tree.
uv run python tools/generate_benchmark_corpus.py --output .tmp/brainstem-bench --files 10000

# Record JSON evidence. Compare only the same machine and corpus.
uv run python tools/benchmark_index.py --path .tmp/brainstem-bench --runs 5 --output benchmark.json
```

[`native/`](native/) contains the Rust/C++/assembly ingest module and the offline Go AST analyzer. CI compiles both. Python re-verifies native bytes and digests before graph construction, and remains the safe fallback even after native wheels ship.

## Evidence-gated delivery

The workflow system connects a design, plan, implementation, executed verification, and independent review. It does not accept a model saying that code is finished as evidence.

```bash
uv run brainstem workflow start "Fix the OAuth callback" --mode high-risk --path /path/to/repository
uv run brainstem workflow status fix-the-oauth-callback --path /path/to/repository
uv run brainstem workflow verify-run fix-the-oauth-callback --path /path/to/repository
```

The full MCP surface includes repository evidence, local memory and skills, team composition, workflow evidence, and controlled actions. Use `brainstem host doctor` to exercise the real local stdio handshake.

## Security is an architectural boundary

| Concern | Brainstem control |
| --- | --- |
| Source exposure | Local filesystem state and local stdio MCP; no Brainstem HTTP service by default. |
| Capability creep | Read-only default and explicit permission grants. |
| Sensitive file leakage | Bounded packets skip sensitive filenames and cap fallback source reads. |
| Stale decisions | Memory can be hash-bound to source; stale references are excluded. |
| Third-party MCP | Credential-free catalog, HTTPS-or-loopback remote policy, and explicit host-side composition; Brainstem never proxies peer tools. |
| Model spending | Per-call input/output limits, response-semantic cache keys, and a prompt-free local usage ledger. |
| Unverifiable completion | Workflow completion requires executed verification after implementation and an approved review. |
| Supply-chain visibility | Locked dependencies, deterministic SBOM generation, CodeQL, Dependabot, secret scanning, and release checks. |

Brainstem is not a compliance certification and does not replace access controls, code review, or secure-development practice.

## Install

Brainstem requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/faizalmunna/brainstem.git
cd brainstem
uv sync --extra dev
uv run brainstem --help
```

### Docker

```bash
docker build --tag brainstem:local .
docker run --rm brainstem:local --help
```

Mount only the target project when using Docker. Indexing writes its local `.brain/` state, so that mount must be writable.

### npm launcher

The scoped npm package is an installer/launcher for the locked Python runtime, not a second Node.js implementation. It remains intentionally unpublished until the maintainer explicitly completes registry authentication.

```bash
# Available after the first public npm release:
npm install -g @faizalmunna/brainstem
brainstem --help
```

## Keep public claims synchronized

The README inventory marker is generated from the MCP tool decorators, bundled skill registry, and host adapters. CI rejects stale facts.

```bash
uv run python tools/update_readme_facts.py --check
uv lock --check
uv run pytest
uv run brainstem release check --path .
```

## Public boundaries

- Security reports: [private GitHub vulnerability reporting](https://github.com/faizalmunna/brainstem/security/advisories/new)
- Source and issues: [github.com/faizalmunna/brainstem](https://github.com/faizalmunna/brainstem)
- Public repository content excludes private development notes, local plans, transcripts, credentials, and private evaluation cases.

See [SECURITY.md](SECURITY.md) for reporting and release controls.

## License

[MIT](LICENSE)
