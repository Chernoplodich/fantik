# Production deployment

Базовый `docker-compose.yml` — prod-ready: resource limits, log rotation,
security hardening, ни один порт не публикуется на 0.0.0.0. Поверх него
накатывается `docker-compose.dev.yml` для разработки. На проде применяется
**только** базовый файл.

## Что включено в базе

| Защита | Реализация |
|---|---|
| Изоляция сети | bridge `fantik_internal`, без implicit-default network |
| Никаких публичных портов | bot/worker/postgres/redis/meili — без `ports:`. Связь только во внутренней сети |
| Resource limits | `deploy.resources.{limits,reservations}` на каждом сервисе |
| Лимит памяти Redis | `--maxmemory 384mb --maxmemory-policy allkeys-lru` |
| Log rotation | `json-file` driver с `max-size: 10m`, `max-file: 5` |
| Security | `security_opt: no-new-privileges`, `cap_drop: ALL` |
| Read-only root | прикладные сервисы (bot/worker/scheduler/migrate) + tmpfs `/tmp` |
| Healthchecks | postgres / redis / meili / worker / worker-broadcast / scheduler |
| Graceful shutdown | `stop_grace_period: 60s` для bot/worker, 30s для deps |

## Resource limits per service

| Сервис | CPU limit | RAM limit | RAM reservation |
|---|---|---|---|
| postgres | 2.0 | 2 GiB | 512 MiB |
| redis | 1.0 | 512 MiB | 64 MiB |
| meilisearch | 1.5 | 1 GiB | 256 MiB |
| bot | 1.0 | 768 MiB | 192 MiB |
| worker | 1.5 | 768 MiB | 192 MiB |
| worker-broadcast | 1.0 | 512 MiB | 128 MiB |
| scheduler | 0.5 | 384 MiB | 96 MiB |
| migrate | 0.5 | 256 MiB | — |
| prometheus | 1.0 | 1 GiB | 128 MiB |
| grafana | 0.5 | 384 MiB | 64 MiB |
| alertmanager | 0.25 | 192 MiB | — |

Суммарный потолок (без observability): **~6.5 GiB RAM, ~7.5 vCPU**.
Минимальная prod-VM: 8 GiB RAM / 4 vCPU. С observability добавляются ~1.5 GiB.

## Подготовка машины к запуску

1. **Установить Docker Engine 24+** и Docker Compose plugin v2.20+.
2. **Создать пользователя `fantik`** (не запускать compose от root):
   ```bash
   useradd -m -s /bin/bash fantik && usermod -aG docker fantik
   ```
3. **Склонировать репозиторий** в `/opt/fantik` (или куда удобно).
4. **Заполнить `.env`** из `.env.example` (см. ниже).
5. **Сгенерировать секреты:**
   ```bash
   # Postgres password
   openssl rand -base64 24 > /tmp/pg_pass && chmod 600 /tmp/pg_pass
   # Meili master key (32+ chars)
   openssl rand -base64 32 > /tmp/meili_key && chmod 600 /tmp/meili_key
   # Grafana admin password (если используется --profile observability)
   openssl rand -base64 24 > /tmp/grafana_pass && chmod 600 /tmp/grafana_pass
   # Webhook secret (если BOT_RUN_MODE=webhook)
   openssl rand -hex 32 > /tmp/webhook_secret && chmod 600 /tmp/webhook_secret
   ```
   Скопировать значения в `.env`, потом удалить временные файлы.
6. **Закрыть `.env` правами 600:**
   ```bash
   chmod 600 .env
   chown fantik:fantik .env
   ```

## Минимальный .env для прода

```env
APP_ENV=prod
LOG_LEVEL=INFO
LOG_RENDERER=json
RELEASE=v1.0.0                       # CI заполнит git sha

BOT_TOKEN=<from @BotFather>
ADMIN_TG_IDS=<your tg id>            # потом ролями через бота

# Polling — если нет публичного домена. Для webhook см. ниже.
BOT_RUN_MODE=polling

POSTGRES_PASSWORD=<openssl rand -base64 24>
MEILI_MASTER_KEY=<openssl rand -base64 32>

# Sentry в проде обязателен — ловит ошибки без логов.
SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project>
SENTRY_TRACES_SAMPLE_RATE=0.05

# Grafana — только при --profile observability.
GRAFANA_ADMIN_PASSWORD=<openssl rand -base64 24>
```

## Запуск

```bash
# 1. Сборка образа (или pull из registry, если REGISTRY+VERSION заданы)
docker compose build

# 2. Поднимаем стек (миграции применяются автоматически контейнером migrate)
docker compose up -d

# 3. Smoke-test всех сервисов
make smoke
```

Проверка что ни один порт не открыт наружу:
```bash
docker compose ps --format 'table {{.Service}}\t{{.Ports}}'
```
В колонке `Ports` должны быть только внутренние порты (`8080-8081/tcp`,
`5432/tcp` и т.д.) **без** `0.0.0.0:...->...`. Если видишь `0.0.0.0` —
скорее всего случайно подключён `docker-compose.dev.yml`.

## Webhook-режим

Telegram webhook требует публичный HTTPS endpoint. Базовый compose НЕ включает
reverse-proxy — поднимай отдельно (nginx / caddy / traefik) перед `bot`-сервисом
и проксируй `/webhook/...` на `bot:8080`. Минимальный nginx-снippet:

```nginx
server {
  listen 443 ssl http2;
  server_name bot.example.com;
  ssl_certificate     /etc/letsencrypt/live/bot.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/bot.example.com/privkey.pem;

  location /webhook/ {
    proxy_pass http://127.0.0.1:8080/webhook/;
    proxy_set_header Host $host;
    proxy_read_timeout 30s;
  }

  # /healthz и /metrics — НЕ открывать наружу. Доступ через ssh-tunnel.
}
```

В `.env`:
```env
BOT_RUN_MODE=webhook
WEBHOOK_BASE_URL=https://bot.example.com
WEBHOOK_SECRET=<openssl rand -hex 32>
```

И в `docker-compose.override.yml` (локально на проде, не коммитить):
```yaml
services:
  bot:
    ports: ["127.0.0.1:8080:8080"]   # nginx работает на хосте
```

Альтернатива — поднять nginx как ещё один сервис в этой же `fantik_internal`
сети, тогда `bot` остаётся без host-портов.

## Observability

Запуск:
```bash
docker compose --profile observability up -d
```

UI биндятся **только на 127.0.0.1**:
- Grafana: `127.0.0.1:3000` — login `admin`, пароль из `GRAFANA_ADMIN_PASSWORD`.
- Prometheus: `127.0.0.1:9090` — без auth, не проксировать наружу без auth-прокси.
- Alertmanager: `127.0.0.1:9093` — то же.

Доступ с лаптопа: `ssh -L 3000:localhost:3000 -L 9090:localhost:9090 fantik@host`.

## Бэкапы

См. [`backup.md`](backup.md). Кратко:
- `scripts/backup_pg.sh` запускается из cron на хосте каждый день, делает
  `pg_dump -Fc | gzip` и держит 30 ротаций.
- Бэкапы лежат вне Docker volumes — на локальном диске или S3.
- Восстановление через `scripts/restore_drill.sh` на staging-БД.

## Алерты, runbook

См. [`runbook.md`](runbook.md). Базовый набор алертов — Telegram + Sentry:
- BotHighErrorRate
- BotHandlerLatencyP95High
- TGApiBadResponses
- ModerationQueueTooDeep
- BroadcastStalled
- OutboxLagHigh
- WorkerQueueBacklog

## Чек-лист перед прод-запуском

- [ ] `.env` создан, права 600, владелец fantik:fantik.
- [ ] Все секреты сгенерированы через `openssl rand`, не копипастили из примеров.
- [ ] `BOT_TOKEN` и `ADMIN_TG_IDS` совпадают с реальной средой.
- [ ] `SENTRY_DSN` указан — ошибки полетят в Sentry, не теряем.
- [ ] Cron на хосте: `scripts/backup_pg.sh` каждый день.
- [ ] `docker compose ps` — ни одного порта на `0.0.0.0`.
- [ ] `make smoke` зелёный.
- [ ] Если webhook — DNS, TLS-сертификат, nginx proxy готовы и проверены.
- [ ] Telegram webhook URL зарегистрирован: бот сам сделает `setWebhook` при старте.
- [ ] При первом запуске прошли миграции (`docker compose logs migrate`) и
      Meili создал индекс с правильными `searchableAttributes`.
- [ ] Если делаешь полный реиндекс после восстановления данных — запускай
      task `full_reindex` через worker-shell.
