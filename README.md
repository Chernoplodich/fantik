# Fantik

Telegram-бот для создания и чтения фанфиков: модерация, умный поиск, рассылки, трекинг.

Полная документация — в [`docs/`](docs/) ([docs/README.md](docs/README.md) — индекс).
Ключевые архитектурные решения и правила разработки — в [`CLAUDE.md`](CLAUDE.md).

## Статус

**Этап 0 + 1 реализованы.** Поднимается полный стек, работает `/start` с UTM-трекингом, онбординг с согласием с правилами, профиль и установка ника автора. Модерация, чтение, поиск и рассылки — в последующих этапах ([`docs/16-roadmap.md`](docs/16-roadmap.md)).

## Стек (коротко)

Python 3.12 · aiogram 3.27 · SQLAlchemy 2 (async) + asyncpg · PostgreSQL 16 · Redis 7 · Meilisearch 1.11 · TaskIQ · dishka (DI) · structlog · Docker Compose.

Обоснование — [`docs/02-stack-and-rationale.md`](docs/02-stack-and-rationale.md).

## Быстрый старт

```bash
# 1) получить токен бота у @BotFather, узнать свой tg_id у @userinfobot
cp .env.example .env
# отредактировать .env: BOT_TOKEN, POSTGRES_PASSWORD, MEILI_MASTER_KEY, ADMIN_TG_IDS

# 2) собрать образы, применить миграции, поднять стек
make build
make migrate
make up

# 3) написать боту /start — должен ответить приветствием и правилами
make logs-bot        # смотреть логи
make ps              # статус контейнеров

# 4) остановить
make down
# полный снос с данными:
make clean
```

Или одной командой:

```bash
make init            # создаст .env из примера, соберёт и запустит
# после заполнения .env:
make init            # повторный вызов — build + migrate + up
```

## Разработка

```bash
make sync            # uv sync: установить зависимости в .venv
make fmt             # ruff format
make lint            # ruff + mypy + import-linter
make test-unit       # unit-тесты локально
make test            # все тесты в контейнере с PG/Redis/Meili
make precommit-install
```

Hot-reload через `docker-compose.dev.yml`: `src/` монтируется в контейнеры, при изменениях достаточно `make restart-bot`.

## Структура

```
fantik/
├── docs/                      # 18 файлов проектной документации
├── CLAUDE.md                  # контекст и гардрейлы для Claude Code
├── src/app/
│   ├── core/                  # config (pydantic-settings), logging (structlog), DI (dishka)
│   ├── domain/                # чистый Python: entities, value objects, events
│   ├── application/           # use cases + порты (Protocol)
│   ├── infrastructure/        # db (SQLAlchemy 2 async), redis, telegram, tasks (TaskIQ)
│   └── presentation/
│       ├── bot/               # aiogram: routers, middlewares, filters, keyboards, FSM
│       └── worker/            # TaskIQ entrypoints: main, broadcast_main, scheduler_main
├── migrations/versions/       # Alembic (0001_init: users, tracking, справочники)
├── tests/                     # unit + integration (testcontainers)
├── docker/                    # Dockerfile + nginx sites
├── docker-compose.yml         # базовый стек
├── docker-compose.dev.yml     # overlay для разработки
├── pyproject.toml             # uv managed, ruff+mypy+pytest конфиг
├── alembic.ini
├── importlinter.ini           # архитектурные контракты (domain purity и т.д.)
├── Makefile                   # типовые команды
└── .env.example               # все переменные окружения с комментариями
```

Подробнее — [`docs/04-modules.md`](docs/04-modules.md).

## Сервисы в Compose

| Сервис | Назначение | Порт |
|---|---|---|
| `postgres` | PostgreSQL 16 | 5432 (dev only) |
| `redis` | кэш, FSM, broker TaskIQ | 6379 (dev only) |
| `meilisearch` | поиск | 7700 (dev only) |
| `bot` | aiogram (polling/webhook) | 8080 (health/metrics) |
| `worker` | TaskIQ default queue | — |
| `worker-broadcast` | TaskIQ broadcast queue с rate-limit | — |
| `scheduler` | TaskIQ scheduler для отложенных задач | — |
| `migrate` | разовый прогон `alembic upgrade head` | — |

## Health-check

`curl http://localhost:8080/healthz` → `ok`
`curl http://localhost:8080/readyz` → JSON с `pg/redis` статусами
`curl http://localhost:8080/metrics` → Prometheus метрики

## Переменные окружения

Полный список — [`.env.example`](.env.example). Самые важные:

- `BOT_TOKEN` — токен от @BotFather
- `ADMIN_TG_IDS` — CSV tg_id админов (для них автоматически выставится роль `admin`)
- `POSTGRES_PASSWORD`
- `MEILI_MASTER_KEY` (мин. 32 символа для production-режима Meilisearch)
- `BOT_RUN_MODE=polling|webhook`

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) — lint + mypy + import-linter + тесты с PG/Redis/Meili в services. Прогоняется на push/PR в `main`/`develop`.

## Лицензия

Proprietary (см. `pyproject.toml`).
