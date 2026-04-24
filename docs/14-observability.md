# 14 · Observability

## Три столпа

1. **Логи** — structlog JSON.
2. **Метрики** — prometheus-client, экспорт по HTTP `/metrics`.
3. **Трейсы** — опционально OpenTelemetry + Sentry performance.

## Логи

### Конфиг structlog

```python
# app/core/logging.py
import logging
import structlog

def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            scrub_pii,  # наш процессор
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def scrub_pii(_, __, event_dict):
    for key in ("first_name", "last_name", "full_name", "text", "caption"):
        event_dict.pop(key, None)
    return event_dict
```

### Поля событий

Middleware `logging.py` биндит контекст:

```python
structlog.contextvars.bind_contextvars(
    update_id=update.update_id,
    user_id=event.from_user.id if event.from_user else None,
    chat_id=event.chat.id if getattr(event, "chat", None) else None,
)
```

После хэндлера — анбиндим. Это даёт в каждом логе контекст, даже если вызывается `log.info("fsm_state_changed", state="waiting_chapter_text")`.

### Уровни

- `DEBUG` — только dev.
- `INFO` — нормальные события (handler invoked, use case succeeded, task completed).
- `WARNING` — нештатное, но автоматически восстановимое (rate limit hit, retryable TG error).
- `ERROR` — ошибка, требует внимания.
- `CRITICAL` — отказ критичной зависимости.

### Пример события

```json
{
  "timestamp": "2026-04-21T09:32:11.123Z",
  "level": "info",
  "event": "fanfic_approved",
  "update_id": 912345,
  "user_id": 12345,
  "fic_id": 42,
  "moderator_id": 999,
  "latency_ms": 37,
  "logger": "app.application.moderation.approve"
}
```

### Куда пишем

- stdout контейнера → Docker logs → Loki/ELK (если подключены) / journalctl.
- Ротация — на уровне Docker (driver `json-file` с лимитами) или logrotate на системе.

## Метрики

### Exporter

Все метрики определены централизованно в [`src/app/core/metrics.py`](../src/app/core/metrics.py) — импорт оттуда, чтобы не было двойной регистрации в `REGISTRY`.

`/metrics` в боте — внутри aiohttp-приложения здоровья ([`src/app/presentation/bot/health.py`](../src/app/presentation/bot/health.py)), порт 8081 (`METRICS_PORT`).

В worker-процессах — `prometheus_client.start_http_server(port)` в daemon-thread, поднимается при импорте entry-point'а (TaskIQ-CLI импортирует его после `execvp`; thread живёт столько же, сколько worker). Порт задаётся env-переменной `FANTIK_WORKER_METRICS_PORT`:
- worker: 8082
- worker-broadcast: 8083
- scheduler: 8084

Docker healthcheck воркеров дёргает именно `/metrics` (если отвечает — процесс жив).

### Стандартные метрики

- Python runtime (GC, memory, threads) — из prometheus-client по умолчанию.

### Кастомные метрики (bot)

```python
from prometheus_client import Counter, Histogram, Gauge

UPDATES_TOTAL = Counter(
    "bot_updates_total", "Received updates", ["type"]
)
HANDLER_LATENCY = Histogram(
    "bot_handler_duration_seconds",
    "Handler latency",
    ["handler", "result"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HANDLER_ERRORS = Counter(
    "bot_handler_errors_total", "Handler errors", ["handler", "error_type"]
)
TG_API_CALLS = Counter(
    "bot_tg_api_calls_total", "Calls to Telegram Bot API", ["method", "result"]
)
TG_API_DURATION = Histogram(
    "bot_tg_api_duration_seconds", "TG API call duration", ["method"]
)
RATE_LIMIT_HITS = Counter(
    "bot_rate_limit_hits_total", "Throttle kicked in", ["scope"]  # user/global
)
```

### Кастомные метрики (worker)

```python
TASK_DURATION = Histogram(
    "worker_task_duration_seconds", "Task duration", ["task", "result"]
)
TASK_RETRIES = Counter("worker_task_retries_total", "Retries", ["task"])
QUEUE_DEPTH = Gauge("worker_queue_depth", "Pending tasks", ["queue"])
```

### Кастомные метрики (broadcast)

```python
BROADCAST_DELIVERIES = Counter(
    "broadcast_deliveries_total", "Broadcast deliveries", ["status"]  # sent/failed/blocked
)
BROADCAST_BUCKET_WAIT = Histogram(
    "broadcast_bucket_wait_seconds", "Time waited for token"
)
```

### Кастомные метрики (домен)

```python
MODERATION_QUEUE_DEPTH = Gauge("moderation_queue_depth", "Pending moderation items", ["kind"])
MODERATION_DECISIONS = Counter("moderation_decisions_total", "Decisions", ["decision"])
MODERATION_DECISION_LATENCY = Histogram(
    "moderation_decision_latency_seconds", "From submit to decide"
)

FIC_PUBLISHED = Counter("fanfics_published_total", "Published fanfics")
CHAPTER_PUBLISHED = Counter("chapters_published_total", "Published chapters")
```

### Инвентарь бизнес-метрик

- `users_total` — gauge, обновляется `metrics_refresh_tick` (cron `* * * * *`).
- `active_users_24h` — gauge, считается из `users.last_seen_at >= now() - '24h'`.
- `fics_approved_total` — gauge (считается по `fanfics.status='approved'`).
- `search_queries_total{backend}` — counter.
- `search_cache_hits_total` / `search_cache_misses_total` — counters. Ratio собирается на стороне Prometheus: `hits / (hits + misses)`.
- `outbox_oldest_pending_age_seconds` — gauge, возраст самой старой неопубликованной записи в `outbox` (для alert `OutboxLagHigh`).

`metrics_refresh_tick` ([`src/app/infrastructure/tasks/metrics_refresh.py`](../src/app/infrastructure/tasks/metrics_refresh.py)) также обновляет `MODERATION_QUEUE_DEPTH{kind}` и `WORKER_QUEUE_DEPTH{queue}` (LLEN на Redis).

## Tracing (опционально)

- OpenTelemetry instrumentation для SQLAlchemy, aiohttp, redis, meilisearch.
- Отправка в Tempo/Jaeger/Sentry Performance.
- Сэмплинг 1% (адекватно для bot-нагрузки).

В MVP трейсы не обязательны; логи + метрики — достаточно. Настраиваем при первой необходимости «понять, где тормозит».

## Sentry

```python
sentry_sdk.init(
    dsn=settings.sentry_dsn,
    environment=settings.env,
    release=settings.release,
    traces_sample_rate=0.01,
    send_default_pii=False,
    integrations=[
        AsyncioIntegration(),
        SqlalchemyIntegration(),
        RedisIntegration(),
    ],
    before_send=drop_pii,
)
```

Подключается к error-handler aiogram и TaskIQ error middleware.

## Health & readiness

`aiohttp` мини-сервер в bot (и worker):

```python
async def healthz(_): return web.Response(text="ok")

async def readyz(_):
    checks = {
        "pg": await ping_pg(),
        "redis": await ping_redis(),
        "meili": await ping_meili(),
    }
    ok = all(checks.values())
    return web.json_response(checks, status=200 if ok else 503)
```

Kubernetes / Docker healthchecks указывают на `/healthz`; оркестратор по `/readyz` может не давать трафик.

## Dashboards (Grafana)

Готовые JSON-дашборды лежат в [`docker/grafana/dashboards/`](../docker/grafana/dashboards/) и провижинятся автоматически при `make up-obs` (compose-profile `observability`). Provisioning-конфиги — в [`docker/grafana/provisioning/`](../docker/grafana/provisioning/).

Пресеты:

1. **Bot health**
   - RPS апдейтов (UPDATES_TOTAL rate)
   - p50/p95/p99 latency (HANDLER_LATENCY)
   - Error rate
   - Rate-limit hits

2. **TG API**
   - Call rate by method
   - p95 latency by method
   - Error rate (429, 403, 400)

3. **Workers**
   - Queue depth
   - Task duration p95
   - Retries
   - Failures

4. **Broadcast**
   - Deliveries per sec
   - Bucket wait p95
   - Blocked ratio

5. **Domain**
   - Moderation queue depth
   - Decision latency
   - Publications per day
   - Active users

## Алерты

Правила в `prometheus/alerts.yml`:

```yaml
groups:
- name: bot
  rules:
  - alert: BotHighErrorRate
    expr: rate(bot_handler_errors_total[5m]) > 0.1
    for: 5m
    annotations:
      summary: "Bot error rate > 10%"
  - alert: ModerationQueueTooDeep
    expr: moderation_queue_depth > 50
    for: 60m
    annotations:
      summary: "Moderation queue > 50 items for 1 hour"
  - alert: TGApiBadResponses
    expr: rate(bot_tg_api_calls_total{result="error"}[5m]) > 1
    for: 5m
  - alert: BroadcastStalled
    expr: rate(broadcast_deliveries_total{status="sent"}[2m]) == 0 and broadcast_status == 1
    for: 5m
```

Алерт канал — Alertmanager → Telegram (в отдельный чат админов).

## Панели в боте (для админа без доступа к Grafana)

- `/admin health` — быстрый JSON от `/readyz` + очередь модерации + размер очереди задач.
- `/admin stats` — уже описано в [`10-tracking-analytics.md`](10-tracking-analytics.md).

## On-call runbook (минимум)

- **Bot error rate > 10%** → смотреть логи, искать top error_type; если Telegram 429 — проверить троттлинг в Redis, снизить rate.
- **Очередь модерации > 50** → уведомить модераторов; при необходимости добавить модератора.
- **Broadcast зависла** → проверить `worker-broadcast` живой; перезапустить; `deliver_one` продолжит с pending.
- **Meili upp?** → fallback автоматически на PG FTS (должен); если нет — reindex.
- **PG full disk** → вакуум, архивация старых партиций.

## Локальная наблюдаемость в dev

- `docker compose logs -f bot` — видим structlog.
- `curl localhost:8080/metrics | grep bot_` — смотрим метрики.
- Прикидочно: разворачивать полный Prometheus/Grafana в dev — избыточно; `docker compose -f ... --profile observability up` может опционально включать их.
