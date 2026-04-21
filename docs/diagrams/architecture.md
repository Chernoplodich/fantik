# Диаграмма компонентов

```mermaid
flowchart TB
    TG[Telegram Bot API]

    subgraph Bot["bot (process 1)"]
        R[Routers]
        MW[Middlewares]
        FSM[FSM Redis storage]
    end

    subgraph Workers["worker / worker-broadcast / scheduler"]
        W1[worker: indexing, repagination, notifications]
        WB[worker-broadcast: global token bucket]
        SC[scheduler: due tasks]
    end

    subgraph Data["stateful services"]
        PG[(PostgreSQL 16)]
        RD[(Redis 7)]
        MS[(Meilisearch)]
    end

    TG <-.polling/webhook.-> Bot
    Bot -->|sendMessage, editMessage, copyMessage| TG

    Bot <-->|FSM, cache, throttle| RD
    Bot <-->|SQLAlchemy async| PG
    Bot -->|publish events| RD

    Workers <-->|TaskIQ broker| RD
    Workers <-->|repos / SQL| PG
    Workers -->|index, query| MS
    WB -->|copyMessage with rate| TG
    SC -->|schedule tasks| RD
    SC -->|partition housekeeping, mv refresh| PG
    Bot -->|search queries| MS

    subgraph Obs["Observability (optional)"]
        PR[Prometheus]
        GR[Grafana]
        SE[Sentry]
    end
    Bot -->|/metrics| PR
    Workers -->|/metrics| PR
    PR --> GR
    Bot --> SE
    Workers --> SE
```

## Потоки

- **Апдейты от пользователей**: Telegram → bot (polling или webhook). Бот быстро отвечает и ставит тяжёлое в TaskIQ.
- **Фоновые задачи**: worker читает из Redis broker, обрабатывает (индексация в Meili, сохранение в PG, отправка уведомления).
- **Рассылки**: отдельный пул `worker-broadcast` с глобальным rate-limit в Redis.
- **Scheduler**: чистит протухшие локи, создаёт партиции, рефрешит materialized views, запускает отложенные рассылки.
- **Наблюдаемость**: Prometheus скрапит метрики с каждого процесса; Grafana строит дашборды; Sentry собирает ошибки.

## Масштабирование

- `bot` при переключении на webhook — горизонтально, за Nginx.
- `worker`, `worker-broadcast` — произвольное число реплик (TaskIQ распределяет).
- `scheduler` — **один активный** (Redis-lock `scheduler:leader:*`).
- `PG`, `Redis`, `Meili` — можно переехать в managed без изменения кода.
