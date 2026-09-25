from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_docker_image_uses_locked_dependencies_and_non_root_runtime():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM ghcr.io/astral-sh/uv:0.11.7@sha256:" in dockerfile
    assert "FROM python:3.11-slim@sha256:" in dockerfile
    assert "WORKDIR /opt/brainstem" in dockerfile
    assert "uv sync --locked --no-dev --no-editable" in dockerfile
    assert "COPY --from=builder /opt/brainstem/.venv /opt/brainstem/.venv" in dockerfile
    assert "FROM builder AS test" in dockerfile
    assert "uv sync --locked --extra dev" in dockerfile
    assert "FROM node:20-bookworm-slim@sha256:" in dockerfile
    assert "FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS npm-test" in dockerfile
    assert "USER brainstem:brainstem" in dockerfile
    assert 'ENTRYPOINT ["brainstem"]' in dockerfile


def test_docker_build_context_excludes_local_state_and_test_artifacts():
    ignored = set((REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())

    assert {".git", ".brain", ".venv", ".npm-sync-test", "work", "debug.log", "tests"} <= ignored
