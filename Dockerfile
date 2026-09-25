# syntax=docker/dockerfile:1
# Build the exact runtime dependency graph recorded in uv.lock, then copy only
# the resulting virtual environment into the small non-root runtime image.
FROM ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a AS uv

FROM python:3.11-slim@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9 AS builder
# Build at the virtualenv's final absolute location. Console-script shebangs
# embed that path, so copying a venv built under another directory would make
# the runtime entrypoint non-executable.
WORKDIR /opt/brainstem
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM builder AS test
# Keep a Linux test path adjacent to the release build. This stage is never
# shipped in the runtime image; it proves the same locked source graph that the
# final image installs.
ARG MCP_TEST_TIMEOUT_S=10
ENV BRAINSTEM_TEST_MCP_TIMEOUT_S=${MCP_TEST_TIMEOUT_S}
COPY tests ./tests
RUN uv sync --locked --extra dev \
    && uv run pytest -q --ignore=tests/test_docker_distribution.py

FROM builder AS arm-test
# QEMU validates installed ARM64 wheels and the portability-critical runtime
# paths. A focused suite keeps this emulated gate practical; native runners
# continue to execute the complete suite.
ARG MCP_TEST_TIMEOUT_S=60
ENV BRAINSTEM_TEST_MCP_TIMEOUT_S=${MCP_TEST_TIMEOUT_S}
COPY tests ./tests
RUN uv sync --locked --extra dev \
    && uv run pytest -q \
        tests/test_cli.py \
        tests/test_indexer.py \
        tests/test_manifest.py \
        tests/test_mcp_stdio.py \
        tests/test_memory.py \
        tests/test_retrieval.py \
        tests/test_skills.py \
        tests/test_task_packet.py

FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS npm-test
# Exercise the published npm artifact in Linux. The wrapper must create its
# own locked Python environment and launch the real CLI without relying on a
# sibling checkout. This test-only stage is excluded from the runtime image.
WORKDIR /workspace
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY npm ./npm
RUN cd npm \
    && npm pack --silent \
    && mkdir -p /tmp/npm-install-smoke \
    && cd /tmp/npm-install-smoke \
    && npm init -y \
    && npm install /workspace/npm/*.tgz \
    && npx --no-install brainstem --help

FROM python:3.11-slim@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9
LABEL org.opencontainers.image.title="Brainstem" \
      org.opencontainers.image.description="Local, model-neutral repository intelligence for MCP coding agents" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/brainstem/.venv/bin:${PATH}"

RUN groupadd --system --gid 10001 brainstem \
    && useradd --system --uid 10001 --gid brainstem --create-home --home-dir /home/brainstem brainstem \
    && mkdir /workspace \
    && chown brainstem:brainstem /workspace

COPY --from=builder /opt/brainstem/.venv /opt/brainstem/.venv

USER brainstem:brainstem
WORKDIR /workspace
ENTRYPOINT ["brainstem"]
CMD ["--help"]
