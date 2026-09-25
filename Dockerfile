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
