import subprocess
import sys

from brainstem.verify import VerificationResult, detect_commands, run_verification


def _py(code: str) -> str:
    # Uses the same Python interpreter running the tests -- no dependency
    # on uv/npm/cargo being installed just to test the runner itself.
    return f'"{sys.executable}" -c "{code}"'


def test_detect_commands_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert detect_commands(tmp_path) == ["uv run pytest -q"]


def test_detect_commands_from_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert detect_commands(tmp_path) == ["npm test"]


def test_detect_commands_returns_empty_when_nothing_recognized(tmp_path):
    assert detect_commands(tmp_path) == []


def test_run_verification_passing_command(tmp_path):
    result = run_verification(tmp_path, [_py("import sys; sys.exit(0)")])
    assert result.passed is True
    assert result.results[0].exit_code == 0


def test_run_verification_failing_command(tmp_path):
    result = run_verification(tmp_path, [_py("import sys; sys.exit(1)")])
    assert result.passed is False
    assert result.results[0].exit_code == 1


def test_run_verification_stops_on_first_failure_by_default(tmp_path):
    result = run_verification(
        tmp_path,
        [_py("import sys; sys.exit(1)"), _py("import sys; sys.exit(0)")],
    )
    assert len(result.results) == 1  # second command never ran


def test_run_verification_runs_all_when_stop_on_failure_false(tmp_path):
    result = run_verification(
        tmp_path,
        [_py("import sys; sys.exit(1)"), _py("import sys; sys.exit(0)")],
        stop_on_failure=False,
    )
    assert len(result.results) == 2
    assert result.passed is False


def test_run_verification_captures_stdout(tmp_path):
    result = run_verification(tmp_path, [_py("print('hello from verify')")])
    assert "hello from verify" in result.results[0].stdout


def test_run_verification_rejects_shell_control_operators_without_running_them(tmp_path):
    marker = tmp_path / "must-not-exist.txt"
    command = _py("print('safe')") + f' > "{marker}"'

    result = run_verification(tmp_path, [command])

    assert result.passed is False
    assert result.results[0].exit_code == -2
    assert "shell control operators" in result.results[0].stderr
    assert marker.exists() is False


def test_run_verification_rejects_explicit_shell_executables(tmp_path):
    result = run_verification(tmp_path, ["cmd /c echo unsafe"])

    assert result.passed is False
    assert result.results[0].exit_code == -2
    assert "shell executable" in result.results[0].stderr


def test_docker_runner_is_restricted_and_uses_no_native_fallback(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr("brainstem.verify.subprocess.run", fake_run)
    result = run_verification(
        tmp_path,
        ["echo verified"],
        runner="docker",
        docker_image="registry.example/brainstem-verify@sha256:" + "a" * 64,
    )

    assert result.passed is True
    argv = calls[0][0]
    assert argv[:5] == ["docker", "run", "--rm", "--pull", "never"]
    assert ["--network", "none"] == argv[argv.index("--network") : argv.index("--network") + 2]
    assert "--read-only" in argv
    assert "--cap-drop" in argv and argv[argv.index("--cap-drop") + 1] == "ALL"
    assert ["--user", "65532:65532"] == argv[argv.index("--user") : argv.index("--user") + 2]
    assert "readonly" in argv[argv.index("--mount") + 1]
    assert argv[-2:] == ["echo", "verified"]


def test_docker_runner_fails_closed_without_an_image(tmp_path):
    result = run_verification(tmp_path, ["echo verified"], runner="docker")

    assert result.passed is False
    assert result.results[0].exit_code == -2
    assert "docker_image" in result.results[0].stderr


def test_docker_runner_rejects_mutable_image_tag(tmp_path):
    result = run_verification(tmp_path, ["echo verified"], runner="docker", docker_image="python:3.13")

    assert result.passed is False
    assert result.results[0].exit_code == -2
    assert "digest-pinned" in result.results[0].stderr


def test_docker_runner_rejects_ambiguous_mount_path(tmp_path):
    repo_root = tmp_path / "unsafe,source"
    repo_root.mkdir()

    result = run_verification(
        repo_root,
        ["echo verified"],
        runner="docker",
        docker_image="registry.example/brainstem-verify@sha256:" + "a" * 64,
    )

    assert result.passed is False
    assert result.results[0].exit_code == -2
    assert "containing ','" in result.results[0].stderr


def test_verification_result_passed_false_when_no_commands():
    assert VerificationResult(results=[]).passed is False
