"""Deterministic verification: run a target repo's own build/lint/test
commands and report real pass/fail with captured output, instead of
trusting an LLM's self-assessment that generated code "looks correct"
(the original vision's Understand->Plan->Implement->Compile->Lint->
Typecheck->Test->...->Repair->Verify pipeline). Nothing in this repo
previously stopped a bad generated change from looking fine to an agent
and being wrong in practice.

Command detection is intentionally simple and override-friendly: a
repo's own [verify] section in brain.toml (manifest.py) is authoritative
when present; otherwise a small set of common project-file signals
produces a reasonable default. Getting this perfectly right for every
ecosystem isn't the goal -- giving a repo owner an easy, obvious way to
configure it correctly once is.

Commands are parsed to an argument vector and run with ``shell=False``. The
MCP path only accepts commands from the repo owner's own brain.toml or
deterministic detection, never arbitrary tool input. Shell operators and shell
executables are rejected rather than becoming an invisible second interpreter.
This is also why MCP verification is gated behind EXECUTE (see
agents/permissions.py), not exposed unconditionally.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_DETECTORS: list[tuple[str, list[str]]] = [
    ("pyproject.toml", ["uv run pytest -q"]),
    ("package.json", ["npm test"]),
    ("Cargo.toml", ["cargo test"]),
    ("go.mod", ["go test ./..."]),
]
_SHELL_EXECUTABLES = {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "sh", "bash", "zsh"}
_DIGEST_PINNED_IMAGE = re.compile(r".+@sha256:[0-9a-f]{64}$", re.IGNORECASE)


def _command_argv(command: str) -> list[str]:
    """Parse a command to argv without asking a shell to interpret it.

    Existing manifests use strings such as ``uv run pytest -q``. Keeping that
    form avoids a destructive config migration, while rejecting pipeline,
    redirect, and command-chain syntax that requires a shell. Quoted arguments
    (including ``python -c`` source) remain valid argv entries.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
    lexer.whitespace_split = True
    argv = list(lexer)
    if not argv:
        raise ValueError("Verification command must not be empty")
    if any(token and set(token) <= {"|", "&", ";", "<", ">"} for token in argv):
        raise ValueError(
            "Verification commands cannot use shell control operators; use one configured command per check."
        )
    if Path(argv[0]).name.lower() in _SHELL_EXECUTABLES:
        raise ValueError("Verification commands cannot invoke a shell executable")
    return argv


def _runner_argv(repo_root: Path, argv: list[str], runner: str, docker_image: str) -> list[str]:
    """Return a native or fail-closed Docker command vector for verification."""
    if runner == "native":
        return argv
    if runner != "docker":
        raise ValueError("Verification runner must be 'native' or 'docker'")
    if not docker_image.strip():
        raise ValueError("Docker verification requires [verify].docker_image")
    if not _DIGEST_PINNED_IMAGE.fullmatch(docker_image):
        raise ValueError("Docker verification requires a digest-pinned image (name@sha256:<64-hex>)")
    # `--pull never` prevents a verification run from silently fetching an
    # unreviewed image. The bind is read-only; writable temporary files stay
    # inside the constrained tmpfs. Any unavailable daemon/image is a normal
    # failed result--there is intentionally no native fallback.
    mount_source = str(repo_root.resolve())
    # Docker's long --mount syntax is comma-delimited and has no portable
    # escaping for a comma in a host path. Refuse that ambiguous case rather
    # than allowing a directory name to alter the mount options.
    if "," in mount_source:
        raise ValueError("Docker verification refuses repository paths containing ',' in mount syntax")
    mount = f"type=bind,src={mount_source},dst=/workspace,readonly"
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65532:65532",
        "--pids-limit",
        "256",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "--mount",
        mount,
        "--workdir",
        "/workspace",
        docker_image,
        *argv,
    ]


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True, slots=True)
class VerificationResult:
    results: list[CommandResult]

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)


def detect_commands(repo_root: Path) -> list[str]:
    """Best-effort default commands from common project-file signals.
    Returns [] if nothing recognizable is found -- an empty list is a
    real, meaningful result (the caller should ask for explicit
    configuration), not an error."""
    for marker, commands in _DETECTORS:
        if (repo_root / marker).exists():
            return commands
    return []


def run_verification(
    repo_root: Path,
    commands: list[str],
    *,
    timeout_s: int = 300,
    stop_on_failure: bool = True,
    runner: str = "native",
    docker_image: str = "",
) -> VerificationResult:
    results: list[CommandResult] = []
    for command in commands:
        start = time.perf_counter()
        try:
            argv = _command_argv(command)
            argv = _runner_argv(repo_root, argv, runner, docker_image)
            proc = subprocess.run(
                argv,
                shell=False,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except ValueError as exc:
            exit_code, stdout, stderr = -2, "", str(exc)
        except OSError as exc:
            exit_code, stdout, stderr = -1, "", str(exc)
        except subprocess.TimeoutExpired as exc:
            exit_code = -1
            stdout = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = f"Command timed out after {timeout_s}s"

        duration = time.perf_counter() - start
        result = CommandResult(
            command=command, exit_code=exit_code, stdout=stdout, stderr=stderr, duration_s=duration
        )
        results.append(result)
        if stop_on_failure and not result.passed:
            break

    return VerificationResult(results=results)
