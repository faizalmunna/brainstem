"""Brainstem's CLI interface for people, scripts, and non-MCP tools."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import typer

from .agents.permissions import Permission
from .agents.profile import agents_dir, load_profile, readonly_profile, save_profile
from .agents.profile import AgentProfile
from .indexer.graph import build_graph, load_graph, save_graph
from .manifest import brain_dir, default_manifest, manifest_path, save_manifest
from .workspace import GRAPH_FILENAME, Workspace


def _open_workspace(path: Path) -> Workspace:
    """`Workspace.open` for every CLI command -- turns the "no brain.toml
    yet" case into a clean one-line error instead of a raw traceback, since
    running any command before `brainstem init` is the single most likely
    first-use mistake for someone new to the tool."""
    try:
        return Workspace.open(path)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None


app = typer.Typer(
    name="brainstem",
    help="A portable AI engineering brain: repo intelligence, memory, and skills for any coding agent.",
    no_args_is_help=True,
)
agent_app = typer.Typer(help="Manage declarative agent profiles (permission grants).")
app.add_typer(agent_app, name="agent")
skill_app = typer.Typer(help="Install/remove/enable/disable individual skills or skill packs.")
app.add_typer(skill_app, name="skill")
team_app = typer.Typer(
    help="Manage declarative agent-team compositions (who does what role). "
    "A host agent reads these and does the actual multi-agent execution -- brainstem never runs one itself."
)
app.add_typer(team_app, name="team")
workflow_app = typer.Typer(help="Run durable, evidence-gated engineering workflows.")
app.add_typer(workflow_app, name="workflow")
host_app = typer.Typer(help="Generate explicit, reviewable local MCP configuration for supported hosts.")
app.add_typer(host_app, name="host")
release_app = typer.Typer(help="Audit source-controlled prerequisites for a Brainstem production release.")
app.add_typer(release_app, name="release")


@app.command()
def init(path: Path = typer.Option(Path("."), "--path", "-p", help="Target repo root.")) -> None:
    """Create the .brain/ directory and a default brain.toml in PATH."""
    repo_root = path.resolve()
    if manifest_path(repo_root).exists():
        typer.echo(f"Already initialized: {manifest_path(repo_root)}")
        raise typer.Exit(code=0)
    manifest = default_manifest(project_name=repo_root.name)
    written = save_manifest(repo_root, manifest)
    (brain_dir(repo_root) / "skills").mkdir(parents=True, exist_ok=True)
    typer.echo(f"Initialized brainstem at {written}")


@app.command()
def index(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Target repo root."),
    embed: bool = typer.Option(
        False, "--embed", help="Also populate the semantic (LanceDB) index. Requires `pip install brainstem[vector]`."
    ),
) -> None:
    """Build (or incrementally update) the repo symbol/dependency graph."""
    from .workspace import VECTOR_DIRNAME

    ws = _open_workspace(path)
    graph_path = brain_dir(ws.repo_root) / GRAPH_FILENAME
    existing = load_graph(graph_path)
    graph = build_graph(ws.repo_root, ws.manifest, existing=existing)
    save_graph(graph, graph_path)
    stats = graph.stats()
    typer.echo(
        f"Indexed {stats['files']} files, {stats['symbols']} symbols, "
        f"{stats['languages']} languages, {stats['edges']} edges -> {graph_path}"
    )

    if embed:
        try:
            from .adapters.lancedb_store import LanceDBVectorStore
        except ImportError:
            typer.echo("--embed requires the 'vector' extra: `pip install brainstem[vector]`", err=True)
            raise typer.Exit(code=1)

        store = LanceDBVectorStore(brain_dir(ws.repo_root) / VECTOR_DIRNAME)
        embedded = 0
        for file_path, node in graph.files.items():
            if not node.symbols:
                continue  # nothing to summarize; skip rather than embed an empty signature
            signature = f"{file_path}: " + ", ".join(f"{s['kind']} {s['name']}" for s in node.symbols)
            store.upsert(file_path, signature, {"language": node.language or ""})
            embedded += 1
        typer.echo(f"Embedded {embedded} file signatures -> {brain_dir(ws.repo_root) / VECTOR_DIRNAME}")


@app.command()
def query(
    question: str = typer.Argument(..., help="What are you trying to find?"),
    path: Path = typer.Option(Path("."), "--path", "-p"),
    limit: int = typer.Option(10, "--limit", "-n"),
    semantic: bool = typer.Option(
        True,
        "--semantic/--no-semantic",
        help="Include the LanceDB/embedding semantic-match layer. First use pays a "
        "one-time embedding-model load cost (several seconds); pass --no-semantic "
        "for fast deterministic-only retrieval (symbol/dependency graph), or use "
        "`brainstem serve` (MCP, long-lived process) to amortize the load once.",
    ),
) -> None:
    """Retrieve the smallest relevant slice of the repo for QUESTION."""
    from .retrieval.engine import RetrievalEngine

    ws = _open_workspace(path)
    if ws.graph is None:
        typer.echo("No index found. Run `brainstem index` first.", err=True)
        raise typer.Exit(code=1)

    engine = RetrievalEngine(ws.graph, ws.vector_store if semantic else None)
    for hit in engine.retrieve(question, limit=limit):
        loc = f":{hit.line}" if hit.line else ""
        sym = f" [{hit.kind}] {hit.symbol}" if hit.symbol else ""
        typer.echo(f"{hit.score:5.2f}  {hit.file}{loc}{sym}   ({hit.reason})")


@app.command("prepare")
def prepare_task(
    task: str = typer.Argument(..., help="Task to compile local evidence for."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
    limit: int = typer.Option(5, "--limit", "-n", help="Maximum direct source hits (1-10)."),
    max_chars: int = typer.Option(8_000, "--max-chars", help="Maximum source characters in the packet."),
    max_packet_chars: int = typer.Option(
        12_000, "--max-packet-chars", help="Hard cap for the complete compact JSON task packet."
    ),
    semantic: bool = typer.Option(
        True,
        "--semantic/--no-semantic",
        help="Include optional semantic candidates in addition to deterministic graph retrieval.",
    ),
) -> None:
    """Compile a bounded, explainable local task packet as JSON.

    This is the CLI equivalent of the MCP ``prepare_task`` tool. It does not
    call an AI provider or write project state.
    """
    from .retrieval.task_packet import build_task_packet

    ws = _open_workspace(path)
    if ws.graph is None:
        typer.echo("No index found. Run `brainstem index` first.", err=True)
        raise typer.Exit(code=1)
    try:
        packet = build_task_packet(
            ws.repo_root,
            ws.graph,
            ws.memory,
            task,
            vector_store=ws.vector_store if semantic else None,
            limit=limit,
            max_chars=max_chars,
            max_packet_chars=max_packet_chars,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(packet, indent=2, sort_keys=True))


@app.command("evaluate")
def evaluate(
    cases: Path = typer.Option(..., "--cases", help="Versioned JSON file containing labelled retrieval cases."),
    path: Path = typer.Option(Path("."), "--path", "-p", help="Target repository root."),
    limit: int = typer.Option(5, "--limit", "-n", help="Retrieved hits to score for each case (1-10)."),
    max_chars: int = typer.Option(8_000, "--max-chars", help="Maximum source characters in each task packet."),
    max_packet_chars: int = typer.Option(
        12_000, "--max-packet-chars", help="Hard cap for each complete compact JSON task packet."
    ),
    semantic: bool = typer.Option(
        False,
        "--semantic/--no-semantic",
        help="Include optional semantic candidates. Default is deterministic-only for reproducible local baselines.",
    ),
) -> None:
    """Measure labelled retrieval quality and complete-packet context reduction locally.

    The report measures exact packet characters, not provider tokens. No case,
    source, result, or repository data is sent to a remote service.
    """
    from .evaluation import evaluate_retrieval, load_evaluation_cases

    ws = _open_workspace(path)
    if ws.graph is None:
        typer.echo("No index found. Run `brainstem index` first.", err=True)
        raise typer.Exit(code=1)
    try:
        suite = load_evaluation_cases(cases)
        report = evaluate_retrieval(
            ws.repo_root,
            ws.graph,
            ws.memory,
            suite,
            vector_store=ws.vector_store if semantic else None,
            limit=limit,
            max_chars=max_chars,
            max_packet_chars=max_packet_chars,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(report, indent=2, sort_keys=True))


@app.command()
def rules(path: Path = typer.Option(Path("."), "--path", "-p")) -> None:
    """List recorded project rules."""
    ws = _open_workspace(path)
    for fact in ws.memory.list(kind="rule"):
        typer.echo(f"- {fact['title']}: {fact['body']}")


@app.command()
def history(
    problem: str = typer.Argument(..., help="Describe the problem to search for."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Search recorded decisions/history for something like PROBLEM."""
    ws = _open_workspace(path)
    for fact in ws.memory.search(problem, kind="history"):
        typer.echo(f"[{fact['created_at']}] {fact['title']}\n    {fact['body']}")


@app.command()
def record(
    kind: str = typer.Argument(..., help="decision | history | rule"),
    title: str = typer.Argument(...),
    body: str = typer.Argument(...),
    paths: str = typer.Option("", "--paths", help="Comma-separated indexed source paths to hash-bind to this fact."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Record a decision, history entry, or rule into local memory."""
    from .memory.references import references_from_csv

    ws = _open_workspace(path)
    try:
        references = references_from_csv(ws.graph, paths)
        fact_id = ws.memory.record(kind, title, body, source="cli", references=references)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Recorded {kind} #{fact_id}: {title} ({len(references)} source reference(s))")


def _workflow_summary(workflow) -> str:
    return (
        f"{workflow.id}: {workflow.state} ({workflow.mode})\n"
        f"  task: {workflow.task}\n"
        f"  artifacts: {len(workflow.artifacts)}"
    )


@workflow_app.command("start")
def workflow_start(
    task: str = typer.Argument(..., help="Outcome to deliver."),
    mode: str = typer.Option("standard", "--mode", help="fast | standard | high-risk"),
    workflow_id: str = typer.Option("", "--id", help="Optional stable workflow id."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Start a workflow; this records work but never starts an agent itself."""
    from .workflow import start_workflow

    ws = _open_workspace(path)
    try:
        workflow = start_workflow(ws.repo_root, task, mode=mode, workflow_id=workflow_id)
    except (ValueError, FileExistsError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(_workflow_summary(workflow))


@workflow_app.command("status")
def workflow_status(
    workflow_id: str = typer.Argument(...),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Show workflow state, artifacts, and the next action."""
    from .workflow import load_workflow, next_work_item

    ws = _open_workspace(path)
    try:
        workflow = load_workflow(ws.repo_root, workflow_id)
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(_workflow_summary(workflow))
    typer.echo(json.dumps(next_work_item(workflow), indent=2))


@workflow_app.command("list")
def workflow_list(path: Path = typer.Option(Path("."), "--path", "-p")) -> None:
    """List saved workflows, newest first."""
    from .workflow import list_workflows

    ws = _open_workspace(path)
    for workflow in list_workflows(ws.repo_root):
        typer.echo(_workflow_summary(workflow))


@workflow_app.command("artifact")
def workflow_artifact(
    workflow_id: str = typer.Argument(...),
    kind: str = typer.Argument(..., help="Examples: context, design, plan, implementation, review."),
    value: str = typer.Argument(..., help="Path or concise evidence summary."),
    status: str = typer.Option("recorded", "--status"),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Record a compact workflow artifact; do not paste whole transcripts."""
    from .workflow import record_artifact

    ws = _open_workspace(path)
    try:
        workflow = record_artifact(ws.repo_root, workflow_id, kind, value, status=status, by="cli")
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Recorded {kind} for {workflow.id} ({len(workflow.artifacts)} artifacts)")


@workflow_app.command("verify")
def workflow_verify(
    workflow_id: str = typer.Argument(...),
    summary: str = typer.Argument(..., help="Command(s) and concise result."),
    passed: bool = typer.Option(..., "--passed/--failed", help="Whether deterministic verification passed."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Record a human attestation; it cannot satisfy a verification gate.

    Use `workflow verify-run` to execute the repository's configured checks
    and create verification evidence that can move the workflow forward.
    """
    from .workflow import record_verification

    ws = _open_workspace(path)
    try:
        workflow = record_verification(ws.repo_root, workflow_id, summary, passed=passed, by="cli", evidence="manual")
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Recorded {'passed' if passed else 'failed'} verification for {workflow.id}")


@workflow_app.command("verify-run")
def workflow_verify_run(
    workflow_id: str = typer.Argument(...),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Run configured verification and bind its actual result to a workflow."""
    from .verify import detect_commands, run_verification
    from .workflow import record_execution_verification

    ws = _open_workspace(path)
    commands = ws.manifest.verify.commands or detect_commands(ws.repo_root)
    if not commands:
        typer.echo("No verify commands configured or detected.", err=True)
        raise typer.Exit(code=1)
    result = run_verification(
        ws.repo_root,
        commands,
        timeout_s=ws.manifest.verify.timeout_s,
        runner=ws.manifest.verify.runner,
        docker_image=ws.manifest.verify.docker_image,
    )
    try:
        workflow = record_execution_verification(ws.repo_root, workflow_id, result, by="cli")
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Recorded executed {'passed' if result.passed else 'failed'} verification for {workflow.id}")
    raise typer.Exit(code=0 if result.passed else 1)


@workflow_app.command("transition")
def workflow_transition(
    workflow_id: str = typer.Argument(...),
    target: str = typer.Argument(..., help="Target workflow state."),
    note: str = typer.Option("", "--note"),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Advance only when required evidence exists."""
    from .workflow import transition_workflow

    ws = _open_workspace(path)
    try:
        workflow = transition_workflow(ws.repo_root, workflow_id, target, by="cli", note=note)
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"{workflow.id}: {workflow.state}")


@host_app.command("config")
def host_config(
    host: str = typer.Argument(..., help="generic | codex | claude-code | cursor | vscode | gemini"),
    profile: str = typer.Option("readonly", "--profile", help="Saved Brainstem profile to grant the host."),
    command: str = typer.Option("brainstem", "--command", help="Installed Brainstem launcher command."),
    path: Path = typer.Option(Path("."), "--path", "-p", help="Target repository root."),
) -> None:
    """Print host configuration; never edits host config files automatically."""
    from .hosts import render_host_config

    try:
        typer.echo(render_host_config(host, path, profile=profile, command=command))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None


@host_app.command("connect-prompt")
def host_connect_prompt(
    profile: str = typer.Option("readonly", "--profile", help="Saved Brainstem profile to grant the host."),
    command: str = typer.Option("brainstem", "--command", help="Installed Brainstem launcher command."),
    path: Path = typer.Option(Path("."), "--path", "-p", help="Target repository root."),
) -> None:
    """Print a safe copy/paste instruction for any MCP-capable AI host."""
    from .hosts import render_connect_prompt

    typer.echo(render_connect_prompt(path, profile=profile, command=command))


@release_app.command("check")
def release_check(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Brainstem source repository root."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Fail closed when required release identity or source controls are absent.

    This command only reads local files and Git metadata. It never publishes,
    contacts a registry, or changes repository state.
    """
    from .release import release_readiness

    report = release_readiness(path)
    if json_output:
        typer.echo(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        for check in report.checks:
            state = "PASS" if check.passed else "FAIL"
            typer.echo(f"{state:4} {check.name}: {check.detail}")
        typer.echo("READY" if report.ready else "NOT READY")
    raise typer.Exit(code=0 if report.ready else 1)


@app.command("sbom")
def sbom(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Brainstem source repository root."),
    output: Path = typer.Option(
        Path("sbom.cdx.json"), "--output", "-o", help="Output JSON path, relative to PATH by default."
    ),
    extra: list[str] = typer.Option([], "--extra", help="Include one declared optional dependency extra; repeatable."),
) -> None:
    """Write a deterministic SBOM from uv.lock; no dependency resolution occurs."""
    from .sbom import write_sbom

    try:
        written = write_sbom(path, output, tuple(extra))
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Wrote SBOM: {written}")


@app.command()
def skills(
    path: Path = typer.Option(Path("."), "--path", "-p"),
    pack: str = typer.Option(None, "--pack", help="Only list skills from this pack, e.g. frontend-react."),
    packs: bool = typer.Option(False, "--packs", help="List available packs instead of individual skills."),
    show_all: bool = typer.Option(False, "--all", help="Include disabled skills (marked [disabled])."),
) -> None:
    """List available skills (bundled + repo-local + installed), optionally scoped to one pack."""
    ws = _open_workspace(path)
    if packs:
        for pack_name in ws.skills.list_packs():
            count = len(ws.skills.list(pack=pack_name))
            typer.echo(f"{pack_name} ({count} skills)")
        return
    for skill in ws.skills.list(pack=pack, include_disabled=show_all):
        marker = "" if ws.skills.is_enabled(skill.name) else " [disabled]"
        typer.echo(f"[{skill.pack}] {skill.name}{marker}: {skill.description}")


@skill_app.command("install")
def skill_install(
    source: str = typer.Argument(..., help="Local directory path or git URL to a skill pack."),
    as_name: str = typer.Option(None, "--as", help="Install under this pack name instead of inferring one from the source."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Install a third-party or your own skill pack (local dir or git URL)."""
    from .skills.manager import install_pack

    ws = _open_workspace(path)
    try:
        pack_name = install_pack(source, ws.repo_root, name=as_name)
    except (FileExistsError, NotADirectoryError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Installed pack '{pack_name}' -> .brain/skills/installed/{pack_name}/")


@skill_app.command("remove")
def skill_remove(
    pack_name: str = typer.Argument(..., help="Name of an installed pack (see `brainstem skills --packs`)."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Remove an installed pack. Never touches bundled or hand-authored repo-local skills."""
    from .skills.manager import remove_pack

    ws = _open_workspace(path)
    try:
        remove_pack(pack_name, ws.repo_root)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Removed pack '{pack_name}'")


@skill_app.command("enable")
def skill_enable(
    name: str = typer.Argument(..., help="Skill name (see `brainstem skills --all`)."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Re-enable a previously disabled skill."""
    from .skills.state import SkillState, state_path

    ws = _open_workspace(path)
    if ws.skills.get(name) is None:
        typer.echo(f"No skill named '{name}' found.", err=True)
        raise typer.Exit(code=1)
    SkillState(state_path(ws.repo_root)).enable(name)
    typer.echo(f"Enabled '{name}'")


@skill_app.command("disable")
def skill_disable(
    name: str = typer.Argument(..., help="Skill name (see `brainstem skills`)."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Hide a skill from listings/agents without deleting it. Works on
    bundled, repo-local, or installed skills alike -- the file is
    untouched; only .brain/skills/state.json changes."""
    from .skills.state import SkillState, state_path

    ws = _open_workspace(path)
    if ws.skills.get(name) is None:
        typer.echo(f"No skill named '{name}' found.", err=True)
        raise typer.Exit(code=1)
    SkillState(state_path(ws.repo_root)).disable(name)
    typer.echo(f"Disabled '{name}' (hidden from listings; the skill file itself is untouched)")


@skill_app.command("record-usage")
def skill_record_usage(
    name: str = typer.Argument(..., help="Skill name."),
    outcome: str = typer.Argument(..., help="success | failure | unclear"),
    notes: str = typer.Option("", "--notes"),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Record whether a skill actually helped for future usage statistics."""
    ws = _open_workspace(path)
    try:
        usage_id = ws.memory.record_skill_usage(name, outcome, notes=notes, source="cli")
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Recorded usage #{usage_id} for '{name}': {outcome}")


@skill_app.command("usage-stats")
def skill_usage_stats(
    name: str = typer.Argument(..., help="Skill name."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Show recorded success/failure counts for a skill."""
    ws = _open_workspace(path)
    stats = ws.memory.skill_usage_stats(name)
    typer.echo(
        f"{stats['skill_name']}: {stats['total_uses']} uses "
        f"({stats['success']} success, {stats['failure']} failure, {stats['unclear']} unclear)"
    )


@app.command()
def serve(
    path: Path = typer.Option(Path("."), "--path", "-p"),
    profile: str = typer.Option(
        None,
        "--profile",
        help="Agent profile name (from .brain/agents/<name>.toml). Omit for the safe read-only profile.",
    ),
) -> None:
    """Start the MCP server (stdio transport) for this repo."""
    from .mcp_server import build_server

    ws = _open_workspace(path)
    if profile:
        agent_profile = load_profile(ws.repo_root, profile)
    else:
        agent_profile = readonly_profile()
        typer.echo(
            "No --profile given: serving with the safe read-only profile. "
            "Create and pass an explicit profile to grant write or execution capability.",
            err=True,
        )
    server = build_server(ws, agent_profile)
    server.run()


@agent_app.command("create")
def agent_create(
    name: str = typer.Argument(..., help="Profile name."),
    permissions: str = typer.Option(
        "READ", "--permissions", help="Comma-separated: READ,WRITE,EXECUTE,NETWORK,INSTALL,DATABASE,DEPLOY,DELETE,SECRET"
    ),
    skills: str = typer.Option("", "--skills", help="Comma-separated skill names this profile may see. Empty = all."),
    description: str = typer.Option("", "--description"),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Create a reusable agent profile (a named, saved permission grant)."""
    ws = _open_workspace(path)
    perm_set = {Permission(p.strip().upper()) for p in permissions.split(",") if p.strip()}
    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    profile = AgentProfile(name=name, description=description, permissions=perm_set, skills=skill_list)
    written = save_profile(ws.repo_root, profile)
    typer.echo(f"Created agent profile '{name}' at {written}")


@agent_app.command("propose")
def agent_propose(
    task: str = typer.Argument(..., help="Plain-language description of what this agent needs to do."),
    name: str = typer.Option("", "--name", help="Profile name. Default: derived from the task description."),
    save: bool = typer.Option(
        False, "--save", help="Persist the proposal immediately instead of only printing it for review."
    ),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Infer a permission grant + relevant skills from a task description
    (deterministic keyword matching, no model call), for a human to review
    before it's ever saved. Without --save this only prints the proposal --
    nothing is written, the same "propose, never auto-register" guardrail
    as `propose_capability`, applied to agent profiles."""
    from .agents.factory import propose_profile

    ws = _open_workspace(path)
    proposal = propose_profile(task, name=name or None, registry=ws.skills)

    typer.echo(f"Proposed profile: {proposal.name}")
    typer.echo(f"  permissions: {', '.join(sorted(p.value for p in proposal.permissions))}")
    for perm, hits in sorted(proposal.rationale.items()):
        typer.echo(f"    {perm} <- matched: {', '.join(hits)}")
    if proposal.matched_skills:
        typer.echo(f"  relevant skills: {', '.join(proposal.matched_skills)}")
    else:
        typer.echo("  relevant skills: none matched")

    if save:
        profile = AgentProfile(
            name=proposal.name,
            description=proposal.description,
            permissions=proposal.permissions,
            skills=proposal.matched_skills,
        )
        written = save_profile(ws.repo_root, profile)
        typer.echo(f"Saved to {written}")
    else:
        typer.echo("Not saved -- rerun with --save to persist, or `agent create` with adjusted permissions.")


@app.command()
def verify(
    path: Path = typer.Option(Path("."), "--path", "-p"),
    command: list[str] = typer.Option(
        None, "--command", "-c", help="Override: run this command instead of the manifest/detected default. Repeatable."
    ),
) -> None:
    """Run this repo's build/lint/test commands and report real pass/fail.

    This is deterministic verification, not an LLM self-assessment. It uses
    [verify].commands from
    brain.toml if set, else a best-effort default from project files
    (pyproject.toml -> pytest, package.json -> npm test, etc.)."""
    from .verify import detect_commands, run_verification

    ws = _open_workspace(path)
    commands = command or ws.manifest.verify.commands or detect_commands(ws.repo_root)
    if not commands:
        typer.echo(
            "No verify commands configured and none could be detected. "
            "Set [verify].commands in .brain/brain.toml or pass --command.",
            err=True,
        )
        raise typer.Exit(code=1)

    result = run_verification(
        ws.repo_root,
        commands,
        timeout_s=ws.manifest.verify.timeout_s,
        runner=ws.manifest.verify.runner,
        docker_image=ws.manifest.verify.docker_image,
    )
    for r in result.results:
        status = "PASS" if r.passed else "FAIL"
        typer.echo(f"[{status}] {r.command}  ({r.duration_s:.1f}s, exit {r.exit_code})")
        if not r.passed:
            if r.stdout.strip():
                typer.echo(r.stdout)
            if r.stderr.strip():
                typer.echo(r.stderr, err=True)

    raise typer.Exit(code=0 if result.passed else 1)


@app.command()
def watch(path: Path = typer.Option(Path("."), "--path", "-p")) -> None:
    """Watch the repo and keep the index incrementally up to date.

    Runs an initial full index, then re-indexes on every batch of file
    changes until interrupted (Ctrl+C). `.brain/` itself and everything in
    the manifest's ignore list are excluded from the watch, so writing the
    graph cache doesn't retrigger itself.
    """
    import watchfiles

    ws = _open_workspace(path)
    graph_path = brain_dir(ws.repo_root) / GRAPH_FILENAME
    ignore_dirs = set(ws.manifest.index.ignore)

    def _watch_filter(change, changed_path: str) -> bool:
        try:
            rel = Path(changed_path).relative_to(ws.repo_root)
        except ValueError:
            return True
        return not any(part in ignore_dirs for part in rel.parts)

    def _reindex() -> None:
        existing = load_graph(graph_path)
        graph = build_graph(ws.repo_root, ws.manifest, existing=existing)
        save_graph(graph, graph_path)
        stats = graph.stats()
        typer.echo(
            f"Indexed {stats['files']} files, {stats['symbols']} symbols, {stats['edges']} edges"
        )

    _reindex()
    typer.echo(f"Watching {ws.repo_root} for changes (Ctrl+C to stop)...")
    for changes in watchfiles.watch(ws.repo_root, watch_filter=_watch_filter):
        typer.echo(f"Detected {len(changes)} change(s), reindexing...")
        _reindex()


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="Prompt to route through the token-efficiency broker."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
    local: bool = typer.Option(False, "--local", help="Prefer the local Ollama backend if it's reachable."),
    ollama_model: str = typer.Option("llama3.2", "--ollama-model", help="Model name as shown by `ollama list`."),
    no_cache: bool = typer.Option(False, "--no-cache"),
) -> None:
    """Run a completion through cache -> route -> call. Exercises the
    broker directly; not part of the MCP tool surface (see broker.py)."""
    from .adapters.ollama import OllamaBackend
    from .broker.broker import RequestBroker
    from .broker.cache import RequestCache
    from .broker.router import NoBackendAvailable, Router

    ws = _open_workspace(path)
    backends = [OllamaBackend(model=ollama_model)]
    try:
        from .adapters.anthropic_backend import AnthropicBackend

        backends.append(AnthropicBackend())
    except ImportError:
        pass
    try:
        from .adapters.openai_backend import OpenAIBackend

        backends.append(OpenAIBackend())
    except ImportError:
        pass

    cache = RequestCache(brain_dir(ws.repo_root) / "cache" / "requests.db")
    router = Router(backends)
    broker = RequestBroker(cache, router)

    try:
        result = broker.complete(prompt, prefer_local=local, use_cache=not no_cache)
    except NoBackendAvailable as exc:
        typer.echo(str(exc), err=True)
        typer.echo("Set ANTHROPIC_API_KEY / OPENAI_API_KEY, or run Ollama locally, then retry.", err=True)
        raise typer.Exit(code=1)

    typer.echo(result.text)
    typer.echo(f"\n[{result.backend}, cache_hit={result.cache_hit}, ~{result.estimated_tokens} tokens]", err=True)


@agent_app.command("list")
def agent_list(path: Path = typer.Option(Path("."), "--path", "-p")) -> None:
    """List saved agent profiles for this repo."""
    ws = _open_workspace(path)
    directory = agents_dir(ws.repo_root)
    if not directory.is_dir():
        typer.echo("No agent profiles defined yet. Use `brainstem agent create`.")
        raise typer.Exit(code=0)
    for toml_path in sorted(directory.glob("*.toml")):
        profile = load_profile(ws.repo_root, toml_path.stem)
        perms = ", ".join(sorted(p.value for p in profile.permissions))
        typer.echo(f"{profile.name}: [{perms}]  {profile.description}")


@team_app.command("create")
def team_create(
    name: str = typer.Argument(..., help="Team name."),
    member: list[str] = typer.Option(
        ..., "--member", help="profile:role, repeatable, e.g. --member architect:planner --member reviewer:critic"
    ),
    description: str = typer.Option("", "--description"),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Create a team: a named set of {agent profile, role} pairs. Each
    profile must already exist (`brainstem agent create`) -- a team
    pointing at nothing isn't useful to a host agent."""
    from .agents.team import AgentTeam, TeamMember, save_team

    ws = _open_workspace(path)
    members = []
    for m in member:
        if ":" not in m:
            typer.echo(f"Invalid --member '{m}', expected profile:role", err=True)
            raise typer.Exit(code=1)
        profile_name, role = m.split(":", 1)
        members.append(TeamMember(profile=profile_name, role=role))

    team = AgentTeam(name=name, description=description, members=members)
    try:
        written = save_team(ws.repo_root, team)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Created team '{name}' at {written}")


@team_app.command("list")
def team_list(path: Path = typer.Option(Path("."), "--path", "-p")) -> None:
    """List saved teams for this repo."""
    from .agents.team import list_teams

    ws = _open_workspace(path)
    names = list_teams(ws.repo_root)
    if not names:
        typer.echo("No teams defined yet. Use `brainstem team create`.")
        return
    for name in names:
        typer.echo(name)


@team_app.command("get")
def team_get(
    name: str = typer.Argument(..., help="Team name."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Show a team's composition (members and their roles)."""
    from .agents.team import load_team

    ws = _open_workspace(path)
    try:
        team = load_team(ws.repo_root, name)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{team.name}: {team.description}")
    for member in team.members:
        typer.echo(f"  - {member.role}: {member.profile}")


@team_app.command("remove")
def team_remove(
    name: str = typer.Argument(..., help="Team name."),
    path: Path = typer.Option(Path("."), "--path", "-p"),
) -> None:
    """Remove a saved team (does not touch the member profiles)."""
    from .agents.team import remove_team

    ws = _open_workspace(path)
    try:
        remove_team(ws.repo_root, name)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Removed team '{name}'")


if __name__ == "__main__":
    app()
