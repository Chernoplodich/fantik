# syntax=docker/dockerfile:1.7
# Единый Dockerfile для bot / worker / scheduler — переключение по ENTRYPOINT_MODULE.

# ---------- builder ----------
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv
COPY --from=ghcr.io/astral-sh/uv:0.4.27 /uv /uvx /usr/local/bin/

# WORKDIR = /app совпадает с runtime — шебанги в .venv/bin/* будут корректны
# при копировании venv "как есть" в runtime-стадию.
WORKDIR /app
COPY pyproject.toml uv.lock* README.md ./
# Ставим prod-зависимости без dev-группы
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
# Финальная синхра ставит сам проект
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 \
      tini \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -r app \
 && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src/ /app/src/
COPY --chown=app:app alembic.ini /app/alembic.ini
COPY --chown=app:app migrations/ /app/migrations/

USER app

ARG ENTRYPOINT_MODULE=app.presentation.bot.main
ENV ENTRYPOINT_MODULE=${ENTRYPOINT_MODULE}

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec python -m $ENTRYPOINT_MODULE"]

EXPOSE 8080 8081
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1
