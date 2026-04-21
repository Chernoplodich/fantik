# 13 · Развертывание (Docker, CI/CD)

## Файлы

```
docker/
├── bot.Dockerfile
├── worker.Dockerfile
└── nginx/
    ├── nginx.conf
    └── sites/default.conf
docker-compose.yml
docker-compose.dev.yml
docker-compose.prod.yml
Makefile
.env.example
.dockerignore
```

## Dockerfile для приложения

Один Dockerfile для bot и worker — меняется только `CMD` (переопределяется в compose). Используем многоэтапную сборку с `uv`.

### `docker/bot.Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# ---------- runtime ----------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 tini curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -r app && useradd -r -g app app
WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY src/ /app/src/
COPY alembic.ini /app/alembic.ini
COPY migrations/ /app/migrations/
USER app
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "app.presentation.bot.main"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8080/healthz || exit 1
```

### `docker/worker.Dockerfile`

Идентичен `bot.Dockerfile`, кроме `CMD`:
```dockerfile
CMD ["python", "-m", "app.presentation.worker.main"]
```

Через arguments можно унифицировать:
```dockerfile
ARG ENTRYPOINT_MODULE=app.presentation.bot.main
ENV ENTRYPOINT_MODULE=${ENTRYPOINT_MODULE}
CMD ["sh", "-c", "python -m $ENTRYPOINT_MODULE"]
```

## docker-compose.yml (base)

```yaml
x-app-env: &app-env
  BOT_TOKEN: ${BOT_TOKEN}
  POSTGRES_DSN: postgresql+asyncpg://fantik:${POSTGRES_PASSWORD}@postgres:5432/fantik
  REDIS_URL: redis://redis:6379/0
  MEILI_URL: http://meilisearch:7700
  MEILI_MASTER_KEY: ${MEILI_MASTER_KEY}
  SENTRY_DSN: ${SENTRY_DSN:-}
  LOG_LEVEL: ${LOG_LEVEL:-INFO}
  TZ: UTC

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: fantik
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: fantik
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "fantik"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "allkeys-lru"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  meilisearch:
    image: getmeili/meilisearch:v1.8
    environment:
      MEILI_MASTER_KEY: ${MEILI_MASTER_KEY}
      MEILI_ENV: production
    volumes:
      - meili_data:/meili_data
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:7700/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  migrate:
    build:
      context: .
      dockerfile: docker/bot.Dockerfile
    environment:
      <<: *app-env
    command: ["alembic", "upgrade", "head"]
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"

  bot:
    build:
      context: .
      dockerfile: docker/bot.Dockerfile
    environment:
      <<: *app-env
      RUN_MODE: polling  # polling | webhook
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
      meilisearch: {condition: service_healthy}
      migrate: {condition: service_completed_successfully}
    restart: unless-stopped

  worker:
    build:
      context: .
      dockerfile: docker/worker.Dockerfile
      args:
        ENTRYPOINT_MODULE: app.presentation.worker.main
    environment:
      <<: *app-env
      WORKER_CONCURRENCY: 4
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
      migrate: {condition: service_completed_successfully}
    restart: unless-stopped

  worker-broadcast:
    build:
      context: .
      dockerfile: docker/worker.Dockerfile
      args:
        ENTRYPOINT_MODULE: app.presentation.worker.broadcast_main
    environment:
      <<: *app-env
      WORKER_CONCURRENCY: 8
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
      migrate: {condition: service_completed_successfully}
    restart: unless-stopped

  scheduler:
    build:
      context: .
      dockerfile: docker/worker.Dockerfile
      args:
        ENTRYPOINT_MODULE: app.presentation.worker.scheduler_main
    environment:
      <<: *app-env
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  meili_data:
```

## docker-compose.dev.yml (overlay)

```yaml
services:
  bot:
    build:
      target: builder
    volumes:
      - ./src:/app/src:cached
    command: ["python", "-m", "watchfiles", "--ignore-paths", "/app/.venv", "python -m app.presentation.bot.main"]
    ports:
      - "8080:8080"

  worker:
    volumes:
      - ./src:/app/src:cached
    command: ["python", "-m", "watchfiles", "--ignore-paths", "/app/.venv", "python -m app.presentation.worker.main"]

  worker-broadcast:
    volumes:
      - ./src:/app/src:cached

  scheduler:
    volumes:
      - ./src:/app/src:cached

  postgres:
    ports:
      - "5432:5432"

  redis:
    ports:
      - "6379:6379"

  meilisearch:
    ports:
      - "7700:7700"
```

Использование: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`.

## docker-compose.prod.yml (overlay)

```yaml
services:
  bot:
    image: registry.example.com/fantik/bot:${VERSION}
    environment:
      RUN_MODE: webhook
      WEBHOOK_URL: https://bot.example.com/webhook/${WEBHOOK_TOKEN_HASH}
      WEBHOOK_SECRET: ${WEBHOOK_SECRET}
    # нет volumes, всё запечено в образ
    deploy:
      resources:
        limits: {cpus: "1.0", memory: 512M}
        reservations: {cpus: "0.25", memory: 128M}

  worker:
    image: registry.example.com/fantik/worker:${VERSION}
    deploy:
      replicas: 2

  worker-broadcast:
    image: registry.example.com/fantik/worker:${VERSION}
    deploy:
      replicas: 4

  nginx:
    image: nginx:alpine
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./docker/nginx/sites:/etc/nginx/conf.d:ro
      - letsencrypt:/etc/letsencrypt:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - bot
    restart: unless-stopped

  postgres:
    # можно заменить на managed — убрать этот сервис и изменить POSTGRES_DSN в env
    image: postgres:16-alpine
    deploy:
      resources:
        limits: {cpus: "2.0", memory: 2G}

volumes:
  letsencrypt:
```

### nginx site config

```nginx
server {
    listen 443 ssl http2;
    server_name bot.example.com;
    ssl_certificate /etc/letsencrypt/live/bot.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.example.com/privkey.pem;

    client_max_body_size 1m;

    location /webhook/ {
        proxy_pass http://bot:8080;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location = /healthz {
        proxy_pass http://bot:8080/healthz;
    }
}
```

## Makefile

```makefile
.PHONY: up down logs ps build rebuild migrate shell test fmt lint

ENV ?= dev

up:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml up -d

down:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml down

logs:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml logs -f --tail=100

ps:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml ps

build:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml build

rebuild:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml build --no-cache

migrate:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml run --rm migrate

migration-new:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml run --rm bot alembic revision --autogenerate -m "$(m)"

shell:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml exec bot python

db-shell:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml exec postgres psql -U fantik

test:
	docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml run --rm bot pytest

fmt:
	uv run ruff format src tests

lint:
	uv run ruff check src tests
	uv run mypy src
```

## `.env.example`

```
# Telegram
BOT_TOKEN=1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
ADMIN_TG_IDS=111,222                # seed админы при первом запуске

# Database
POSTGRES_PASSWORD=changeme

# Meilisearch
MEILI_MASTER_KEY=changeme-min-32-chars-long

# Webhook (prod only)
WEBHOOK_TOKEN_HASH=                 # sha256(BOT_TOKEN)
WEBHOOK_SECRET=changeme

# Sentry (optional)
SENTRY_DSN=

# Logging
LOG_LEVEL=INFO

# Timezone для админских дат
ADMIN_TZ=Europe/Moscow

# Feature flags
SEARCH_BACKEND=meili                # meili | pg
ALLOW_PAID_BROADCAST=false
```

## `.dockerignore`

```
.venv
__pycache__
*.pyc
.git
.gitignore
.env
.env.*
!.env.example
tests/
docs/
.github/
*.md
.ruff_cache
.mypy_cache
.pytest_cache
htmlcov
```

## CI/CD (GitHub Actions)

### `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: {python-version: "3.12"}
      - run: uv sync
      - run: uv run ruff check src tests
      - run: uv run ruff format --check src tests
      - run: uv run mypy src

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: ci
          POSTGRES_DB: fantik_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
        ports: ["6379:6379"]
      meilisearch:
        image: getmeili/meilisearch:v1.8
        env:
          MEILI_MASTER_KEY: ci-secret-32-characters-long-xxxx
          MEILI_NO_ANALYTICS: "true"
        ports: ["7700:7700"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: {python-version: "3.12"}
      - run: uv sync
      - env:
          POSTGRES_DSN: postgresql+asyncpg://postgres:ci@localhost:5432/fantik_test
          REDIS_URL: redis://localhost:6379/0
          MEILI_URL: http://localhost:7700
          MEILI_MASTER_KEY: ci-secret-32-characters-long-xxxx
        run: |
          uv run alembic upgrade head
          uv run pytest --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v4
        with: {file: coverage.xml}

  build-image:
    needs: [lint, test]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ vars.REGISTRY }}
          username: ${{ secrets.REGISTRY_USER }}
          password: ${{ secrets.REGISTRY_PASS }}
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/bot.Dockerfile
          push: true
          tags: |
            ${{ vars.REGISTRY }}/fantik/bot:latest
            ${{ vars.REGISTRY }}/fantik/bot:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    needs: build-image
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to VPS via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /srv/fantik
            export VERSION=${{ github.sha }}
            docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps --wait bot worker worker-broadcast scheduler
```

## Процесс первого запуска

1. `cp .env.example .env` — заполнить `BOT_TOKEN`, `POSTGRES_PASSWORD`, `MEILI_MASTER_KEY`, `ADMIN_TG_IDS`.
2. `make build`.
3. `make migrate`.
4. `make up`.
5. Написать боту `/start` — проверка работоспособности.
6. Залогиниться под админом (чей `tg_id` в `ADMIN_TG_IDS`) — меню `/admin` доступно.
7. Создать первый тестовый фанфик как автор.

## Smoke-скрипты

В `scripts/smoke.sh`:

```bash
#!/usr/bin/env bash
set -e
curl -f http://localhost:8080/healthz
curl -f http://localhost:8080/readyz
docker compose exec -T postgres psql -U fantik -c 'SELECT count(*) FROM users;'
docker compose exec -T redis redis-cli ping
curl -fs -H "Authorization: Bearer $MEILI_MASTER_KEY" http://localhost:7700/indexes | jq
echo "OK"
```

Запускается в CI как post-deploy.

## Расширения / альтернативы

- **Managed PG/Redis/Meili**: убрать сервисы из Compose, изменить `POSTGRES_DSN`/`REDIS_URL`/`MEILI_URL` в `.env`.
- **Kubernetes**: Helm-чарт с теми же сервисами, HPA на воркеры по `taskiq_queue_depth`.
- **Swarm**: `docker stack deploy` c тем же compose.
- **Мониторинг**: добавить `prometheus` и `grafana` сервисы — скрапят `/metrics` от bot/worker.

## Секретность prod

- SSH-доступ к VPS только по ключам.
- `.env` на VPS с правами `600`, владелец — deploy user.
- PostgreSQL только внутри docker network, порт не прокинут наружу.
- Nginx с TLS 1.3 only, HSTS, rate-limit на `/webhook/` (100 r/s).
