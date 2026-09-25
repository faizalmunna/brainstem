"""Local stdio MCP tools for focused repository intelligence.

The server intentionally provides bounded, permission-checked project
evidence instead of unrestricted raw filesystem access. Capability and agent
profile proposals require explicit human review before they are persisted.
"""

from __future__ import annotations

import hashlib
import json

from fastmcp import FastMCP

from .agents.permissions import PermissionDenied, require_permission as _enforce_permission
from .agents.profile import AgentProfile, agents_dir, load_profile, readonly_profile
from .audit import record_audit
from .retrieval.context import MAX_BUNDLE_HITS, build_context_bundle
from .retrieval.task_packet import DEFAULT_PACKET_CHARS, DEFAULT_PACKET_TOTAL_CHARS, build_task_packet
from .memory.store import REPO_SCOPE, agent_scope
from .retrieval.engine import RetrievalEngine
from .workspace import Workspace


def build_server(ws: Workspace, profile: AgentProfile | None = None) -> FastMCP:
    # An MCP server is a capability boundary.  An omitted profile must never
    # silently turn a newly connected agent into an administrator.
    profile = profile or readonly_profile()
    mcp: FastMCP = FastMCP("brainstem")

    def require_permission(tool_name: str, agent_profile: AgentProfile) -> None:
        """Enforce the permission table and record denied MCP capability use.

        The audit contains only actor/tool/outcome plus a digest of the error;
        it never stores task text, source excerpts, or arguments that might
        contain sensitive repository data.
        """
        try:
            _enforce_permission(tool_name, agent_profile)
        except PermissionDenied as exc:
            try:
                record_audit(
                    ws.repo_root,
                    action=f"mcp.{tool_name}",
                    actor=f"mcp:{agent_profile.name}",
                    outcome="denied",
                    detail=str(exc),
                )
            except OSError:
                # Never turn an audit filesystem failure into an allowed tool
                # call, nor hide the original permission denial.
                pass
            raise

    @mcp.tool()
    def describe_project() -> dict:
        """Summarize this project: name, indexed size, languages present."""
        require_permission("describe_project", profile)
        stats = ws.graph.stats() if ws.graph else {"files": 0, "symbols": 0, "languages": 0, "edges": 0}
        return {
            "name": ws.manifest.project.name,
            "root": str(ws.repo_root),
            "indexed": ws.graph is not None,
            "agent_profile": profile.name,
            **stats,
        }

    @mcp.tool()
    def get_rules() -> list[dict]:
        """Return this project's recorded rules/conventions."""
        require_permission("get_rules", profile)
        return ws.memory.list(kind="rule")

    @mcp.tool()
    def query_context(question: str, limit: int = 10) -> list[dict]:
        """Return the smallest relevant slice of the repo for `question`,
        instead of requiring the caller to load whole files."""
        require_permission("query_context", profile)
        if ws.graph is None:
            return []
        engine = RetrievalEngine(ws.graph, ws.vector_store)
        return [
            {
                "file": hit.file,
                "symbol": hit.symbol,
                "kind": hit.kind,
                "line": hit.line,
                "score": hit.score,
                "reason": hit.reason,
            }
            for hit in engine.retrieve(question, limit=limit)
        ]

    @mcp.tool()
    def get_context_bundle(question: str, limit: int = 5, max_chars: int = 12_000) -> dict:
        """Return small, line-numbered source excerpts for a question.

        This is the preferred repository-intelligence call when an agent
        needs code rather than just result metadata.  It is read-only,
        resolves paths inside the repository only, and caps the returned
        text to prevent accidental whole-repository context loading.
        """
        require_permission("get_context_bundle", profile)
        if not 1 <= limit <= MAX_BUNDLE_HITS:
            return {"error": f"limit must be between 1 and {MAX_BUNDLE_HITS}"}
        if ws.graph is None:
            return {"excerpts": [], "total_chars": 0, "truncated": False, "skipped": 0}
        engine = RetrievalEngine(ws.graph, ws.vector_store)
        try:
            bundle = build_context_bundle(
                ws.repo_root, engine.retrieve(question, limit=limit), max_chars=max_chars
            )
        except ValueError as exc:
            return {"error": str(exc)}
        indexed_files = [
            {
                "file": excerpt["file"],
                "content_hash": ws.graph.files[excerpt["file"]].content_hash,
                "start_line": excerpt["start_line"],
                "end_line": excerpt["end_line"],
                "char_count": excerpt["char_count"],
            }
            for excerpt in bundle["excerpts"]
            if excerpt["file"] in ws.graph.files
        ]
        fingerprint = hashlib.sha256(json.dumps(indexed_files, sort_keys=True).encode()).hexdigest()
        bundle["context_manifest"] = {"index_fingerprint": fingerprint, "files": indexed_files}
        return bundle

    @mcp.tool()
    def prepare_task(
        task: str,
        limit: int = 5,
        max_chars: int = DEFAULT_PACKET_CHARS,
        max_packet_chars: int = DEFAULT_PACKET_TOTAL_CHARS,
    ) -> dict:
        """Compile small, explainable local evidence before coding a task.

        This is the preferred first call for implementation, debugging, or
        review work. It combines bounded current-source excerpts with the
        local dependency graph, matching tests, project rules, relevant local
        memory, Git change metadata, risk signals, and an index-freshness
        check. It never calls a model, writes repository state, or exposes
        sensitive source files.
        """
        require_permission("prepare_task", profile)
        if ws.graph is None:
            return {
                "error": "No index found. Run `brainstem index` before preparing a task.",
                "packet_version": 1,
            }
        try:
            return build_task_packet(
                ws.repo_root,
                ws.graph,
                ws.memory,
                task,
                vector_store=ws.vector_store,
                limit=limit,
                max_chars=max_chars,
                max_packet_chars=max_packet_chars,
            )
        except ValueError as exc:
            return {"error": str(exc), "packet_version": 1}

    @mcp.tool()
    def find_related(file_or_symbol: str, limit: int = 10) -> list[dict]:
        """Find files/symbols related to a given file path or symbol name,
        including direct dependency-graph neighbors (imports/imported-by)."""
        require_permission("find_related", profile)
        if ws.graph is None:
            return []
        engine = RetrievalEngine(ws.graph, ws.vector_store)
        return [
            {"file": hit.file, "symbol": hit.symbol, "kind": hit.kind, "score": hit.score, "reason": hit.reason}
            for hit in engine.retrieve(file_or_symbol, limit=limit)
        ]

    @mcp.tool()
    def check_history(problem: str, limit: int = 10, mine_only: bool = False) -> list[dict]:
        """Search recorded decisions/bug-history for something like `problem`.
        `mine_only=True` restricts to this connection's own agent-scoped
        memory (see record_decision's `private` flag) rather than
        everything recorded for the repo."""
        require_permission("check_history", profile)
        scope = agent_scope(profile.name) if mine_only else None
        return ws.memory.search(problem, kind="history", limit=limit, scope=scope)

    @mcp.tool()
    def list_skills(pack: str | None = None) -> list[dict]:
        """List skills available in this repo (bundled + repo-local),
        optionally filtered to one pack (see `list_skill_packs`), and
        filtered to this agent profile's `skills` grant when non-empty."""
        require_permission("list_skills", profile)
        allowed = set(profile.skills) or None
        return [
            {"name": s.name, "description": s.description, "triggers": s.triggers, "pack": s.pack}
            for s in ws.skills.list(pack=pack)
            if allowed is None or s.name in allowed
        ]

    @mcp.tool()
    def list_skill_packs() -> list[str]:
        """List the skill packs available in this repo (e.g. 'frontend-react',
        'qa-playwright') -- use with list_skills(pack=...) to browse one domain
        instead of the full list."""
        require_permission("list_skills", profile)
        return ws.skills.list_packs()

    @mcp.tool()
    def list_agents() -> list[dict]:
        """List declarative agent profiles saved for this repo
        (`.brain/agents/*.toml`, created via `brainstem agent create` or
        `agent propose --save`). See `propose_agent_profile` for
        synthesizing a new one from a task description instead of
        hand-authoring it.
        """
        require_permission("list_agents", profile)
        directory = agents_dir(ws.repo_root)
        if not directory.is_dir():
            return []
        results = []
        for toml_path in sorted(directory.glob("*.toml")):
            saved = load_profile(ws.repo_root, toml_path.stem)
            results.append(
                {
                    "name": saved.name,
                    "description": saved.description,
                    "permissions": sorted(p.value for p in saved.permissions),
                    "skills": saved.skills,
                }
            )
        return results

    @mcp.tool()
    def propose_agent_profile(task_description: str, name: str = "") -> dict:
        """Infer a permission grant + relevant skills for a task
        description (deterministic keyword matching, no model call,
        no persistence). Returns a proposal for a human to review; nothing
        is saved by this call. To actually create the profile, a human
        runs `brainstem agent create` (or `agent propose --save`) --
        deliberately CLI-only, the same boundary as skill installation,
        since persisting a new permission grant needs a human in the loop,
        not an agent approving its own capability request.
        """
        require_permission("propose_agent_profile", profile)
        from .agents.factory import propose_profile

        proposal = propose_profile(task_description, name=name or None, registry=ws.skills)
        return {
            "name": proposal.name,
            "description": proposal.description,
            "permissions": sorted(p.value for p in proposal.permissions),
            "rationale": proposal.rationale,
            "matched_skills": proposal.matched_skills,
            "status": "proposed_not_saved",
        }

    @mcp.tool()
    def record_decision(
        title: str, body: str, tags: str = "", private: bool = False, paths: str = ""
    ) -> dict:
        """Persist an architectural/engineering decision for future agents
        to find. `private=True` scopes it to this connection's own agent
        profile (see check_history's `mine_only`) instead of the whole
        repo -- for something specific to this agent's own working
        context rather than a repo-wide decision. Optionally pass indexed,
        comma-separated `paths` to bind the decision to current source hashes;
        stale referenced decisions are excluded from future task packets."""
        require_permission("record_decision", profile)
        from .memory.references import references_from_csv

        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        scope = agent_scope(profile.name) if private else REPO_SCOPE
        references = references_from_csv(ws.graph, paths)
        fact_id = ws.memory.record(
            "decision", title, body, tags=tag_list, source=f"mcp:{profile.name}", scope=scope, references=references
        )
        return {"id": fact_id, "recorded": True, "scope": scope, "references": len(references)}

    @mcp.tool()
    def list_teams() -> list[str]:
        """List declarative agent-team compositions saved for this repo
        (`.brain/agents/teams/*.toml`, created via `brainstem team
        create`). Use with get_team(name) to see a team's actual member
        profiles/roles/permissions -- a host agent uses this to know who
        to spawn for a multi-agent task; brainstem doesn't spawn or
        execute them itself."""
        require_permission("list_teams", profile)
        from .agents.team import list_teams as _list_teams

        return _list_teams(ws.repo_root)

    @mcp.tool()
    def get_team(name: str) -> dict:
        """Return a team's members, each resolved with its actual
        permissions and skill grants, so a host agent has everything it
        needs to spawn the right subagents without a second lookup per
        member."""
        require_permission("get_team", profile)
        from .agents.profile import load_profile as _load_profile
        from .agents.team import load_team

        try:
            team = load_team(ws.repo_root, name)
        except FileNotFoundError as exc:
            return {"error": str(exc)}
        members = []
        for member in team.members:
            member_profile = _load_profile(ws.repo_root, member.profile)
            members.append(
                {
                    "role": member.role,
                    "profile": member.profile,
                    "permissions": sorted(p.value for p in member_profile.permissions),
                    "skills": member_profile.skills,
                    "model_preference": member_profile.model_preference,
                }
            )
        return {"name": team.name, "description": team.description, "members": members}

    @mcp.tool()
    def record_skill_usage(skill_name: str, outcome: str, notes: str = "") -> dict:
        """Record whether a skill actually helped ('success' | 'failure' |
        'unclear'). Lets future agents (via get_skill_usage_stats) see which
        skills have a track record
        of actually working, not just which ones exist."""
        require_permission("record_skill_usage", profile)
        usage_id = ws.memory.record_skill_usage(skill_name, outcome, notes=notes, source=f"mcp:{profile.name}")
        return {"id": usage_id, "recorded": True}

    @mcp.tool()
    def get_skill_usage_stats(skill_name: str) -> dict:
        """Return success/failure counts recorded for a skill via
        record_skill_usage."""
        require_permission("get_skill_usage_stats", profile)
        return ws.memory.skill_usage_stats(skill_name)

    @mcp.tool()
    def start_workflow(task: str, mode: str = "standard", workflow_id: str = "") -> dict:
        """Start a durable engineering workflow (fast, standard, or high-risk).

        This records task state only; it never spawns an agent or grants new
        permissions. Use get_next_work_item to obtain the compact next-action
        packet for the current host or human.
        """
        require_permission("start_workflow", profile)
        from .workflow import next_work_item, start_workflow as _start_workflow

        workflow = _start_workflow(ws.repo_root, task, mode=mode, workflow_id=workflow_id)
        return {"id": workflow.id, "task": workflow.task, "created": True, **next_work_item(workflow)}

    @mcp.tool()
    def get_workflow_state(workflow_id: str) -> dict:
        """Read workflow state and its compact evidence artifacts."""
        require_permission("get_workflow_state", profile)
        from .workflow import load_workflow, next_work_item

        workflow = load_workflow(ws.repo_root, workflow_id)
        return {
            "id": workflow.id,
            "task": workflow.task,
            "state": workflow.state,
            "mode": workflow.mode,
            "artifacts": [artifact.model_dump() for artifact in workflow.artifacts],
            **next_work_item(workflow),
        }

    @mcp.tool()
    def get_next_work_item(workflow_id: str) -> dict:
        """Return the next allowed workflow action without loading a transcript."""
        require_permission("get_next_work_item", profile)
        from .workflow import load_workflow, next_work_item as _next_work_item

        return _next_work_item(load_workflow(ws.repo_root, workflow_id))

    @mcp.tool()
    def record_workflow_artifact(
        workflow_id: str, kind: str, value: str, status: str = "recorded"
    ) -> dict:
        """Record a concise design, plan, implementation, or approved-review artifact."""
        require_permission("record_workflow_artifact", profile)
        from .workflow import record_artifact

        workflow = record_artifact(
            ws.repo_root, workflow_id, kind, value, status=status, by=f"mcp:{profile.name}"
        )
        return {"id": workflow.id, "recorded": kind, "artifact_count": len(workflow.artifacts)}

    @mcp.tool()
    def record_workflow_verification(workflow_id: str, summary: str, passed: bool) -> dict:
        """Record a human attestation; it cannot satisfy a verification gate.

        Use run_workflow_verification for actual, gate-satisfying execution.
        """
        require_permission("record_workflow_verification", profile)
        from .workflow import record_verification

        workflow = record_verification(
            ws.repo_root, workflow_id, summary, passed=passed, by=f"mcp:{profile.name}", evidence="manual"
        )
        return {"id": workflow.id, "passed": passed, "artifact_count": len(workflow.artifacts)}

    @mcp.tool()
    def run_workflow_verification(workflow_id: str) -> dict:
        """Execute configured verification and bind hashes/results to a workflow.

        This uses only repository-configured or detected commands and is the
        only MCP workflow verification tool whose passed result can unlock
        review/completion.
        """
        require_permission("run_workflow_verification", profile)
        from .verify import detect_commands, run_verification as _run_verification
        from .workflow import record_execution_verification

        commands = ws.manifest.verify.commands or detect_commands(ws.repo_root)
        if not commands:
            return {"passed": False, "error": "No verify commands configured or detected", "results": []}
        result = _run_verification(
            ws.repo_root,
            commands,
            timeout_s=ws.manifest.verify.timeout_s,
            runner=ws.manifest.verify.runner,
            docker_image=ws.manifest.verify.docker_image,
        )
        workflow = record_execution_verification(ws.repo_root, workflow_id, result, by=f"mcp:{profile.name}")
        return {
            "id": workflow.id,
            "passed": result.passed,
            "results": [
                {"command": item.command, "exit_code": item.exit_code, "duration_s": round(item.duration_s, 2)}
                for item in result.results
            ],
        }

    @mcp.tool()
    def request_workflow_transition(workflow_id: str, target: str, note: str = "") -> dict:
        """Move workflow state only when its required verification/review evidence exists."""
        require_permission("request_workflow_transition", profile)
        from .workflow import next_work_item, transition_workflow

        workflow = transition_workflow(ws.repo_root, workflow_id, target, by=f"mcp:{profile.name}", note=note)
        return {"id": workflow.id, "state": workflow.state, **next_work_item(workflow)}

    @mcp.tool()
    def propose_capability(name: str, description: str) -> dict:
        """Propose a new skill/tool. Never auto-registered: this only
        records the proposal for human review. Self-extension must pass
        sandboxing, tests, a security check, and explicit human approval
        before anything is added to the shared skill library.
        """
        require_permission("propose_capability", profile)
        fact_id = ws.memory.record("proposal", name, description, source=f"mcp:{profile.name}")
        return {"id": fact_id, "status": "pending_human_review"}

    @mcp.tool()
    def run_verification(commands: list[str] | None = None) -> dict:
        """Run this repo's build/lint/test commands and report real
        pass/fail with output, not a self-assessment. Uses [verify].commands
        from brain.toml, or
        a best-effort detected default. For safety, MCP callers cannot
        substitute arbitrary shell commands: an explicitly supplied list
        must exactly equal the configured/detected command list.
        Requires EXECUTE: this runs real shell commands from the repo's
        own trusted config, gated the same way any other side-effecting
        capability is.
        """
        require_permission("run_verification", profile)
        from .verify import detect_commands, run_verification as _run_verification

        cmds = ws.manifest.verify.commands or detect_commands(ws.repo_root)
        if not cmds:
            return {"passed": False, "error": "No verify commands configured or detected", "results": []}
        if commands is not None and commands != cmds:
            return {
                "passed": False,
                "error": "MCP verification only runs repository-configured commands. "
                "Set [verify].commands in .brain/brain.toml; use the local CLI for an explicit one-off command.",
                "results": [],
            }

        result = _run_verification(
            ws.repo_root,
            cmds,
            timeout_s=ws.manifest.verify.timeout_s,
            runner=ws.manifest.verify.runner,
            docker_image=ws.manifest.verify.docker_image,
        )
        return {
            "passed": result.passed,
            "results": [
                {
                    "command": r.command,
                    "passed": r.passed,
                    "exit_code": r.exit_code,
                    "duration_s": round(r.duration_s, 2),
                    "stdout": r.stdout[-4000:],
                    "stderr": r.stderr[-4000:],
                }
                for r in result.results
            ],
        }

    return mcp


def main() -> None:
    """`python -m brainstem.mcp_server` entry point, using CWD as the repo root."""
    import sys
    from pathlib import Path

    try:
        ws = Workspace.open(Path("."))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    build_server(ws).run()


if __name__ == "__main__":
    main()
