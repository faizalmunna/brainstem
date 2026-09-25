# syntax=docker/dockerfile:1
# Build the exact runtime dependency graph recorded in uv.lock, then copy only
# the resulting virtual environment into the small non-root runtime image.
FROM ghcr.io/astral-sh/uv:0.11.7 AS uv

FROM python:3.11-slim AS builder
WORKDIR /build
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.11-slim
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

COPY --from=builder /build/.venv /opt/brainstem/.venv

USER brainstem:brainstem
WORKDIR /workspace
ENTRYPOINT ["brainstem"]
CMD ["--help"]
