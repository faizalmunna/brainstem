<!-- brainstem-readme-facts: mcp_tools=25; bundled_skills=997; skill_packs=92; hosts=6 -->
<!-- brainstem-readme-hosts: generic,codex,claude-code,cursor,vscode,gemini -->

<p align="center">
  <img src="assets/brainstem-agent-flow.gif" alt="Animated guide: Brainstem maps a local repository, focuses the task evidence, then gives a coding agent controlled tools and workflow evidence." width="100%" />
</p>

<h1 align="center">Brainstem</h1>

<p align="center">
  <strong>Give every coding agent the right slice of a real repository—without loading the whole thing.</strong><br />
  <sub>Local repository intelligence · bounded evidence · explicit control</sub>
</p>

<p align="center">
  <a href="https://github.com/faizalmunna/brainstem/actions/workflows/ci.yml"><img src="https://github.com/faizalmunna/brainstem/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <a href="https://github.com/faizalmunna/brainstem/actions/workflows/codeql.yml"><img src="https://github.com/faizalmunna/brainstem/actions/workflows/codeql.yml/badge.svg" alt="CodeQL status" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-7c3aed?style=flat-square" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/MCP-local%20stdio-0ea5e9?style=flat-square" alt="Local stdio MCP" />
  <img src="https://img.shields.io/badge/default-read--only-16a34a?style=flat-square" alt="Read only by default" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Tree--sitter-repository%20parsing-111827?style=for-the-badge" alt="Tree-sitter parsing" />
  <img src="https://img.shields.io/badge/FastMCP-tool%20surface-7c3aed?style=for-the-badge" alt="FastMCP tools" />
  <img src="https://img.shields.io/badge/uv-locked%20runtime-DE5FE9?style=for-the-badge&logo=astral&logoColor=white" alt="uv locked runtime" />
  <img src="https://img.shields.io/badge/Docker-non--root%20runtime-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker runtime" />
  <img src="https://img.shields.io/badge/Node.js-npm%20launcher-339933?style=for-the-badge&logo=nodedotjs&logoColor=white" alt="Node.js npm launcher" />
  <img src="https://img.shields.io/badge/GitHub_Actions-release%20checks-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</p>

<table>
  <tr>
    <td align="center" width="25%"><h2>96.2%</h2><sub>smaller bounded source-context baseline<sup>†</sup></sub></td>
    <td align="center" width="25%"><h2>0.95</h2><sub>Recall@5 on labelled navigation tasks<sup>†</sup></sub></td>
    <td align="center" width="25%"><h2>997</h2><sub>targeted engineering guides</sub></td>
    <td align="center" width="25%"><h2>25</h2><sub>permission-gated MCP tools</sub></td>
  </tr>
</table>

> <strong>Brainstem is the local context layer between a serious codebase and the coding agent you already use.</strong> It maps repository structure, compiles only the evidence a task needs, keeps decisions fresh, and makes high-risk work pass real workflow gates.

## Stop paying the context tax

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🧩 The problem</h3>
      Big repositories do not fit cleanly into a prompt. Whole-file dumping wastes context, hides dependencies, and makes every new agent session rediscover the same project facts.
    </td>
    <td width="33%" valign="top">
      <h3>⚡ The Brainstem move</h3>
      Build a local symbol/dependency map, retrieve the relevant code and tests, then emit a capped, explainable task packet over local stdio MCP.
    </td>
    <td width="33%" valign="top">
      <h3>🛡️ The outcome</h3>
      Agents receive less redundant context, teams retain engineering intent across sessions, and sensitive actions remain permission-checked and auditable.
    </td>
  </tr>
</table>

## Measured context efficiency

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>60,114 → 2,272</h3>
      <strong>average GPT-4o-tokenized source-context input</strong><br />
      Full indexed repository → bounded MCP source bundle
    </td>
    <td width="50%" valign="top">
      <h3>10 labelled questions · Recall@5 0.95 · MRR 0.66</h3>
      Same-repository development baseline, measured 2026-09-25 with the visible source context supplied to the tool.
    </td>
  </tr>
</table>

<sup>†</sup> This is a measured Brainstem-repository navigation baseline, not a universal claim about every codebase, model bill, or agent outcome. It shows how much repeated source context was avoided in that defined run. Run <code>brainstem evaluate</code> on your own labelled tasks to measure your repository.

## Three steps from repository to useful agent context

<pre lang="bash"><code># 1. Create local state and map the repository.
uv run brainstem init --path /path/to/repository
uv run brainstem index --path /path/to/repository

# 2. Give an agent a bounded, fresh task packet.
uv run brainstem prepare "trace the login redirect bug" --path /path/to/repository

# 3. Connect the agent host you already use—read-only by default.
uv run brainstem host config codex --path /path/to/repository --profile readonly
</code></pre>

<p align="center"><sub>Small local state. No Brainstem hosted service by default. No automatic host-configuration edits. No invented token savings.</sub></p>

## The agent ecosystem—open by design

Brainstem gives each host the same local-stdio contract, rather than forcing a
model, cloud account, or IDE migration. It prints reviewable configuration; it
does <strong>not</strong> edit a host's settings behind your back.

| Agent / host | Ready path | What Brainstem adds |
| --- | --- | --- |
| <strong>OpenAI Codex</strong> | <code>.codex/config.toml</code> | Bounded repository evidence and explicit profiles |
| <strong>Claude Code</strong> | <code>claude mcp add-json</code> | Local MCP context, workflow, and retrieval tools |
| <strong>Cursor</strong> | <code>.cursor/mcp.json</code> | A focused project map instead of broad file loading |
| <strong>VS Code</strong> | <code>.vscode/mcp.json</code> | Portable, reviewable local server definition |
| <strong>Gemini CLI</strong> | <code>.gemini/settings.json</code> | The same model-neutral MCP surface |
| <strong>generic / any MCP host</strong> | portable <code>mcpServers</code> JSON | Copy/paste local command contract—no vendor lock-in |

<pre lang="bash"><code># Generate, inspect, then paste the least-privilege configuration you want.
uv run brainstem host config codex --path /path/to/repository --profile readonly

# For another host, generate a portable safe connection instruction.
uv run brainstem host connect-prompt --path /path/to/repository --profile readonly
</code></pre>

<details>
<summary><strong>See the full 25-tool MCP surface</strong></summary>

<br />

| Surface | Tools |
| --- | --- |
| <strong>Repository evidence</strong> | <code>describe_project</code> · <code>get_rules</code> · <code>query_context</code> · <code>get_context_bundle</code> · <code>prepare_task</code> · <code>find_related</code> |
| <strong>Memory & guides</strong> | <code>check_history</code> · <code>list_skills</code> · <code>list_skill_packs</code> · <code>list_agents</code> · <code>propose_agent_profile</code> · <code>record_decision</code> · <code>record_skill_usage</code> · <code>get_skill_usage_stats</code> |
| <strong>Team composition</strong> | <code>list_teams</code> · <code>get_team</code> |
| <strong>Evidence-gated workflow</strong> | <code>start_workflow</code> · <code>get_workflow_state</code> · <code>get_next_work_item</code> · <code>record_workflow_artifact</code> · <code>record_workflow_verification</code> · <code>run_workflow_verification</code> · <code>request_workflow_transition</code> |
| <strong>Controlled actions</strong> | <code>propose_capability</code> · <code>run_verification</code> |

All 25 tools are mapped in one reviewable permission table. A new connection
starts with the <code>readonly</code> profile; a tool without the required grant is
denied and recorded in the local audit trail.

</details>

## Coordinate agent teams with visible responsibilities

Use the host agent or team system you prefer. Brainstem provides named,
reviewable profiles; declarative teams; and an evidence-gated workflow so the
next person or agent sees the required work—not a forgotten chat transcript.

| Role | Next responsibility | Guardrail |
| --- | --- | --- |
| <strong>Explorer</strong> | Retrieve minimal current context | Read-only by default |
| <strong>Designer</strong> | Record a reviewed design | Standard/high-risk work cannot skip it |
| <strong>Planner</strong> | Bind implementation and test plans | Implementation waits for plan evidence |
| <strong>Implementer</strong> | Make one bounded change | Re-verification is required after implementation |
| <strong>Tester</strong> | Run configured verification | Only executed evidence can satisfy the gate |
| <strong>Reviewer</strong> | Approve or return work | High-risk review must be independent |
| <strong>Coordinator</strong> | Route the next work item | Hosts perform execution; Brainstem never silently spawns agents |

<pre lang="bash"><code>uv run brainstem agent propose "test and fix the OAuth callback" --path /path/to/repository
uv run brainstem workflow start "Fix the OAuth callback" --mode high-risk --path /path/to/repository
</code></pre>

## See the evidence behind every packet

<code>prepare</code> combines focused source excerpts, likely tests, repository
rules, Git signals, risk flags, and fresh source-linked memory under a hard
packet limit. If a repository is so small that a complete safe source set is
shorter, <code>--context-mode auto</code> selects that smaller safe form.

<details>
<summary><strong>What the local evaluator reports</strong></summary>

<br />

For each labelled task, <code>evaluate</code> reports Recall@k, first relevant
rank, packet size, indexed source size, and character-level context reduction:

<pre><code>context reduction = 1 − (complete task-packet characters / indexed-source characters)
</code></pre>

Character reduction is deterministic and provider-neutral. Optional tokenizer
counts describe supplied input context; they are never presented as provider
charges. End-to-end model cost and patch quality need controlled agent trials.

<pre lang="bash"><code>uv run brainstem evaluate --path /path/to/repository --cases /path/to/labelled-cases.json
</code></pre>

</details>

## 997 targeted engineering guides, selectable instead of overwhelming

The bundled catalog is a guide library—not material automatically injected into
an agent context. A profile can restrict visible guides; any guide can be
enabled or disabled; and usage outcomes can be recorded locally to find which
guidance actually helps your team.

<pre lang="bash"><code># Browse only names/counts, then open one domain when it is relevant.
uv run brainstem skills --packs --path /path/to/repository
uv run brainstem skills --pack security-owasp --path /path/to/repository
</code></pre>

<details>
<summary><strong>Browse every bundled guide pack (92)</strong></summary>

<br />

<strong>Frontend & mobile</strong>

<code>accessibility-wcag</code> · <code>angular</code> · <code>css-layout-debugging</code> · <code>flutter-dart</code> · <code>frontend-react</code> · <code>pwa-offline</code> · <code>react-native</code> · <code>svelte-sveltekit</code> · <code>vue-nuxt</code> · <code>web-performance-vitals</code>

<strong>Backend & API</strong>

<code>api-versioning-strategy</code> · <code>authentication-authorization-patterns</code> · <code>backend-api-design</code> · <code>background-job-systems</code> · <code>dotnet-aspnet</code> · <code>go-backend-services</code> · <code>grpc-protobuf</code> · <code>java-spring-boot</code> · <code>nodejs-express</code> · <code>php-laravel</code> · <code>python-async-concurrency</code> · <code>ruby-rails</code>

<strong>Data, search & streaming</strong>

<code>data-pipelines-airflow-dbt</code> · <code>data-postgres</code> · <code>data-warehouse-query-optimization</code> · <code>dynamodb-nosql</code> · <code>elasticsearch-search</code> · <code>kafka-streaming</code> · <code>mongodb-nosql</code> · <code>mysql-specific</code> · <code>redis-deep</code>

<strong>Cloud, platform & delivery</strong>

<code>aws-failure-modes</code> · <code>azure-failure-modes</code> · <code>bazel-build-system</code> · <code>cicd-pipeline-design</code> · <code>cloud-cost-optimization</code> · <code>gcp-failure-modes</code> · <code>helm-kubernetes-packaging</code> · <code>incident-response-oncall</code> · <code>infra-containers-k8s</code> · <code>monorepo-turborepo</code> · <code>serverless-lambda-patterns</code> · <code>service-mesh-istio</code> · <code>terraform-iac-deep</code>

<strong>Security & governance</strong>

<code>api-security-deep</code> · <code>cloud-security-posture</code> · <code>compliance-gdpr-soc2</code> · <code>container-security</code> · <code>penetration-testing-methodology</code> · <code>sast-dast-tooling</code> · <code>secrets-management-vault</code> · <code>security-owasp</code> · <code>supply-chain-security</code> · <code>threat-modeling</code>

<strong>Testing & quality</strong>

<code>contract-testing-pact</code> · <code>cypress-e2e</code> · <code>load-performance-testing</code> · <code>mutation-testing-quality</code> · <code>qa-playwright</code> · <code>test-data-management</code> · <code>unit-testing-java</code> · <code>unit-testing-javascript</code> · <code>unit-testing-python</code>

<strong>AI, retrieval & agent reliability</strong>

<code>agent-tool-calling-reliability</code> · <code>llm-prompt-engineering-pitfalls</code> · <code>ml-data-pipeline-quality</code> · <code>ml-model-serving-inference</code> · <code>ml-monitoring-drift-detection</code> · <code>ml-training-fine-tuning-pitfalls</code> · <code>rag-retrieval-debugging</code> · <code>vector-database-tuning</code>

<strong>Systems & performance</strong>

<code>caching-strategy-design</code> · <code>concurrency-race-conditions</code> · <code>distributed-systems-consistency</code> · <code>graphql-deep</code> · <code>memory-leak-diagnosis</code> · <code>observability</code> · <code>performance-profiling-methodology</code> · <code>websockets-realtime</code>

<strong>Engineering practice & product</strong>

<code>cli-tool-design</code> · <code>code-review-heuristics</code> · <code>dependency-upgrade-strategy</code> · <code>desktop-electron-apps</code> · <code>email-deliverability</code> · <code>general</code> · <code>golang-idioms-pitfalls</code> · <code>legacy-code-migration</code> · <code>localization-i18n</code> · <code>payment-processing-billing</code> · <code>python-packaging-dependency-hell</code> · <code>rust-systems-programming</code> · <code>typescript-type-system</code>

</details>

## Security is a boundary, not a footnote

| Concern | Brainstem control |
| --- | --- |
| Source exposure | Local filesystem state and local stdio MCP; no Brainstem HTTP service by default. |
| Agent capability creep | <code>readonly</code> default plus explicit READ, WRITE, EXECUTE, NETWORK, INSTALL, DATABASE, DEPLOY, DELETE, and SECRET grants. |
| Sensitive file leakage | Bounded packets skip sensitive filenames and cap fallback source reads. |
| Stale decisions | Memory can be linked to source hashes; stale references are excluded from future packets. |
| Unverifiable completion | Workflow completion needs executed verification after the most recent implementation and an approved review. |
| Isolated verification | Optional Docker verification is fail-closed: digest-pinned image, read-only source mount, no network, non-root user, dropped capabilities, <code>no-new-privileges</code>, and resource limits. |
| Supply-chain visibility | Locked Python dependency graph, deterministic SBOM generation, CodeQL, Dependabot, secret scanning, push protection, and release checks. |

Brainstem is not a compliance certification and does not replace your access
controls, code review, or secure-development program. It makes those controls
available to the local agent boundary rather than hiding them behind prose.

## Install, connect, and prove it locally

### Source installation

Brainstem requires Python 3.11+ and <a href="https://docs.astral.sh/uv/">uv</a>.

<pre lang="bash"><code>git clone https://github.com/faizalmunna/brainstem.git
cd brainstem
uv sync --extra dev
uv run brainstem --help
</code></pre>

### Docker runtime

The runtime image uses the locked dependency graph and an unprivileged user.

<pre lang="bash"><code>docker build --tag brainstem:local .
docker run --rm brainstem:local --help
</code></pre>

To use it against a project, mount only that project. Indexing writes local
<code>.brain/</code> state, so its mount must be writable.

<pre lang="bash"><code># PowerShell
docker run --rm -it -v "C:\path\to\project:/workspace" brainstem:local init --path /workspace
docker run --rm -it -v "C:\path\to\project:/workspace" brainstem:local index --path /workspace

# bash/zsh: preserve ownership of generated files
docker run --rm -it --user "$(id -u):$(id -g)" -v "$PWD:/workspace" brainstem:local index --path /workspace
</code></pre>

### npm launcher

The scoped npm package is an installer/launcher for the locked Python runtime,
not a second Node.js implementation. It remains intentionally unpublished
until the maintainer explicitly completes registry authentication.

<pre lang="bash"><code># Available after the first public npm release:
npm install -g @faizalmunna/brainstem
brainstem --help
</code></pre>

### Verification commands

<pre lang="bash"><code>uv lock --check
uv run pytest
uv run brainstem release check --path .
</code></pre>

The release gate fails closed when repository identity, a security reporting
channel, dependency locking, or supply-chain controls are missing. Version
tags wait for Windows, Linux, macOS, npm-install, and Docker checks before
release artifacts are built and attested; publication remains an explicit
maintainer action.

## Public boundaries

- Security reports: <a href="https://github.com/faizalmunna/brainstem/security/advisories/new">private GitHub vulnerability reporting</a>
- Source and issues: <a href="https://github.com/faizalmunna/brainstem">github.com/faizalmunna/brainstem</a>
- Public repository content excludes private development notes, local plans,
  transcripts, credentials, and private evaluation cases.

See <a href="SECURITY.md">SECURITY.md</a> for reporting and release controls.

## License

<a href="LICENSE">MIT</a>
