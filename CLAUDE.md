# CLAUDE.md — контекст проекта для Claude Code

Файл автоматически загружается при работе с этим репозиторием. Его задача — сразу ввести в курс дела и **не дать забыть** ключевые решения, принятые на этапе планирования. Детали — в [`docs/`](docs/); здесь — карта и правила.

## Что это за проект

**Fantik** — Telegram-бот для создания и чтения фанфиков с полноценной админкой: модерация, умный поиск, рассылки, трекинг источников трафика.

- **Стадия**: документация v1 готова, код ещё не написан. Стартуем с Этапа 0 в [`docs/16-roadmap.md`](docs/16-roadmap.md).
- **Рабочий каталог**: `/Users/chernoplod/Dev/fantik/`.
- **Не git-репозиторий** на момент старта — при реализации инициализировать.

## Tech stack

| Слой | Выбор |
|---|---|
| Язык | **Python 3.12+** |
| Bot | **aiogram 3.27+** |
| БД | **PostgreSQL 16** + **SQLAlchemy 2.x async** + **asyncpg** + **Alembic** |
| Кэш / FSM / rate-limit / locks / broker | **Redis 7** |
| Поиск | **Meilisearch** (русская токенизация, фасеты) |
| Очереди / scheduler | **TaskIQ** (asyncio-native, Redis broker) |
| DI | **dishka** |
| Config | **pydantic-settings** |
| Логи / метрики / ошибки | **structlog** + **prometheus-client** + **Sentry** |
| Тесты | **pytest** + **pytest-asyncio** + **testcontainers** + **hypothesis** |
| Линт / форматтер / типы | **ruff** + **mypy (strict)** |
| Пакетный менеджер | **uv** |
| Контейнеризация | **Docker** + **docker-compose** |

Обоснование и альтернативы — [`docs/02-stack-and-rationale.md`](docs/02-stack-and-rationale.md).

## Навигация по документации

**Всегда начинай с** [`docs/README.md`](docs/README.md) и [`docs/00-overview.md`](docs/00-overview.md).

| Тема | Файл |
|---|---|
| Цели, роли, допущения, глоссарий | [`docs/00-overview.md`](docs/00-overview.md) |
| Архитектурные принципы и процессы | [`docs/01-architecture.md`](docs/01-architecture.md) |
| Tech stack с обоснованием | [`docs/02-stack-and-rationale.md`](docs/02-stack-and-rationale.md) |
| Схема PostgreSQL, индексы, партиционирование | [`docs/03-data-model.md`](docs/03-data-model.md) |
| Структура `src/app/`, use case'ы, правила импорта | [`docs/04-modules.md`](docs/04-modules.md) |
| User flows (sequence-диаграммы) | [`docs/05-user-flows.md`](docs/05-user-flows.md) |
| Модерация: роли, очередь, причины, аудит | [`docs/06-admin-and-moderation.md`](docs/06-admin-and-moderation.md) |
| **Рассылки (ключевой модуль)** | [`docs/07-broadcast-system.md`](docs/07-broadcast-system.md) |
| Meilisearch: индекс, фасеты, fallback | [`docs/08-search-design.md`](docs/08-search-design.md) |
| **Читалка и пагинатор (UTF-16)** | [`docs/09-reader-pagination.md`](docs/09-reader-pagination.md) |
| UTM-трекинг, воронки, дашборды | [`docs/10-tracking-analytics.md`](docs/10-tracking-analytics.md) |
| Масштабирование, кэши, нагрузочные | [`docs/11-scalability-performance.md`](docs/11-scalability-performance.md) |
| Безопасность, PII, валидация | [`docs/12-security-privacy.md`](docs/12-security-privacy.md) |
| Docker, compose, CI/CD, Makefile | [`docs/13-deployment-docker.md`](docs/13-deployment-docker.md) |
| Логи, метрики, алерты | [`docs/14-observability.md`](docs/14-observability.md) |
| Уровни тестов, инструменты, покрытие | [`docs/15-testing.md`](docs/15-testing.md) |
| Этапы поставки, чеклисты | [`docs/16-roadmap.md`](docs/16-roadmap.md) |
| Диаграммы (architecture, ERD, sequences) | [`docs/diagrams/`](docs/diagrams/) |

## Ключевые архитектурные решения (НЕ отступать без обсуждения)

1. **Layered Architecture**: `domain → application → infrastructure/presentation`. Правила импорта в [`docs/04-modules.md`](docs/04-modules.md). Проверяется через `import-linter` в CI.
2. **Broadcast через `bot.copy_message(from_chat_id=admin, message_id=source)`** — не пересобираем сообщение вручную. Клавиатура накладывается параметром `reply_markup`. Детали — [`docs/07-broadcast-system.md`](docs/07-broadcast-system.md).
3. **Entities хранятся как Telegram API JSON** в `jsonb`. Никаких HTML/MarkdownV2 конверсий. Отдача — через `send_message(text=..., entities=[...])`.
4. **UTF-16 offsets** в MessageEntity. Python string index ≠ entity offset. Все операции над entities проходят через `infrastructure/telegram/entity_utils.py`. Подробно — [`docs/09-reader-pagination.md`](docs/09-reader-pagination.md).
5. **Materialized `chapter_pages`** — страницы строятся воркером после публикации/правки, не при каждом открытии.
6. **`SELECT FOR UPDATE SKIP LOCKED`** для очереди модерации. Никаких Redis-lock'ов для этого.
7. **4 процесса**: `bot`, `worker`, `worker-broadcast` (с глобальным token-bucket 25 msg/s в Redis), `scheduler` (singleton через Redis leader-lock).
8. **Outbox-паттерн** для гарантированной публикации доменных событий после commit.
9. **Event-driven индексация Meilisearch** через TaskIQ. Публикация не ждёт индексации.
10. **Любая правка approved-фика → `pending`** целиком. Без разделения «минорные / мажорные».
11. **first-touch атрибуция** UTM (`users.utm_source_code_id` не перезаписывается).

## Стандартные допущения (зафиксированы, меняются только по запросу)

- Максимум глав на фик: 200; максимум символов на главу: 100 000 (UTF-16 units).
- Максимум UTF-16 units на страницу в читалке: **3 900** (запас 196 до лимита 4 096).
- Rate-limit broadcast: **25 msg/s** (буфер от лимита TG 30 msg/s).
- Anti-flood per user: **30 апдейтов/мин** через token-bucket в Redis.
- TTL FSM: 1 час. TTL кэша страниц: 1 час. TTL кэша ролей: 60 сек.
- Хранение времени: UTC. UI таймзона по умолчанию: `Europe/Moscow`.
- Язык UI: RU. i18n-слой готов, словари пока только ru.
- Медиа в фиках: **только обложка** (`sendPhoto`, JPEG/PNG, ≤ 5 МБ). В главах — только текст + entities + custom emoji.
- `author_nick`: 2–32 символа, `[a-z0-9_-]`, UNIQUE по `LOWER(author_nick)`.
- Один ник автора на все работы пользователя.

## Структура проекта (будущая)

```
fantik/
├── docs/                  # эта документация (готово)
├── CLAUDE.md              # этот файл
├── src/app/               # код приложения (см. docs/04-modules.md)
│   ├── core/              # config, logging, DI, errors
│   ├── domain/            # pure Python, без SQLAlchemy/aiogram
│   ├── application/       # use cases + porty (Protocol)
│   ├── infrastructure/    # db, redis, search, tasks, telegram
│   └── presentation/      # bot (routers/middlewares/fsm/keyboards), worker
├── migrations/            # Alembic
├── tests/                 # unit / integration / e2e / load
├── docker/
├── docker-compose*.yml
├── pyproject.toml         # uv managed
├── uv.lock
├── alembic.ini
├── Makefile
├── .env.example
├── .github/workflows/ci.yml
└── README.md
```

## Текущий статус (обновляй по мере реализации)

- [x] Сбор требований и уточнения с пользователем
- [x] Research best practices (aiogram 3, Meilisearch, broadcast, pagination)
- [x] Написание документации в `docs/` (18 файлов)
- [x] **Этап 0** — скелет проекта (pyproject, Docker, линтеры, CI, core, DI-контейнер)
- [x] **Этап 1** — users + tracking + онбординг (`/start`, согласие с правилами, установка `author_nick`, `/admin`/`/mod` роли через seed)
- [x] **Этап 2** — авторство + модерация (создание/правка фика, главы, submit/cancel/revise, очередь SKIP LOCKED, approve/reject с 7 причинами, audit_log, outbox, уведомления автору)
- [x] **Этап 3** — читалка + пагинатор (`ChapterPaginator` с UTF-16 split + свойствами hypothesis, таблицы `bookmarks` / `likes` / `reads_completed` / `reading_progress`, Redis-кэш страниц на msgpack, TaskIQ `repaginate_chapter` + минимальный outbox-диспетчер на `fanfic.approved`, роутеры `reader` / `browse` / `shelf`, каталог «Новое»/«Топ»/«По фэндому», атомарные счётчики `fanfics.likes_count` и `fanfics.reads_completed_count`)
- [x] **Этап 4** — поиск + каталог (Meilisearch-адаптер `MeiliSearchIndex` с circuit-breaker + jitter, `application/search/` pure-ports и use cases `SearchUseCase`/`SuggestUseCase`/`IndexFanficUseCase`, TaskIQ `index_fanfic` / `full_reindex` / `delete_from_index` + расширенный outbox-диспетчер на `fanfic.approved|edited|archived`, `TaskiqSearchIndexQueue` с per-fic Redis-дебаунсом для `ToggleLike`, PG FTS-fallback через `chapters.tsv_text` + UI-баннер `degraded`, инлайн-режим `@bot <query>` с Redis-кэшем 60с и deep-link `?start=fic_<id>`, меню фильтров с мультиселектом фандомов/возраста/тегов/сортировки и курсорной пагинацией, `settings_bootstrap` применяется идемпотентно при старте bot-процесса)
- [x] **Этап 5** — социалка (миграция 0006: `subscriptions` / `reports` / `notifications` + ENUMы `report_target` / `report_status`, домен `subscriptions` + `reports` с событиями `UserSubscribedToAuthor` / `ReportSubmitted` / `ReportHandled`, use cases `SubscribeUseCase` / `UnsubscribeUseCase` / `NotifySubscribersUseCase` (fanout чанками по 100 + batch-INSERT) и `CreateReportUseCase` (self-report запрещён, анти-дубль open-жалоб) / `HandleReportUseCase` / `ListOpenReportsUseCase`, TaskIQ `notify_new_chapter` / `notify_new_work` / `deliver_notification` / `notify_moderation_decision` + `TaskiqNotificationQueue` c Redis token-bucket `tb:notifications` 25 msg/s, outbox-диспетчер различает fanout по `kind` в `fanfic.approved` (`fic_first_publish` → new_work, `chapter_add` → new_chapter, edit-кейсы без рассылки) и роутит `report.handled` → `notify_moderation_decision` при `notify_reporter=true`; `TelegramForbiddenError` → silent skip без retry; роутеры `subscriptions.py` и `reports.py` + FSM `ReportFlow` (причина → коммент), кнопки «🔔 Подписаться / 🔕 Отписаться» и «⚠️ Жалоба» на карточке фика и странице читалки, вкладка «⚠️ Жалобы» в меню модератора с Dismiss / Action-архивация фика)
- [x] **Этап 6** — админка (миграция 0008: `broadcasts` + `broadcast_deliveries` на 16 hash-партициях + 4 materialized views `mv_daily_activity` / `mv_top_fandoms_7d` / `mv_author_stats` / `mv_moderator_load` с UNIQUE-индексами под `REFRESH CONCURRENTLY` + ENUMы `bc_status` / `bcd_status`; миграция 0009: `users.blocked_bot_at` + частичный индекс `ix_users_active_not_blocked`; домен `Broadcast` со state-machine (`draft → scheduled|running|cancelled`, `scheduled → running|cancelled`, `running → finished|cancelled|failed`) и чистая `interpret_segment` на 6 kind'ов; use cases `CreateBroadcastDraft` / `SetKeyboard` (wizard-парсер «текст\|url» + auto-capture `message.reply_markup` из forwarded-сообщения, пропуск шага клавиатуры если кнопки уже есть) / `SetSegment` / `Schedule` / `Launch` / `Cancel` / `EnumerateRecipients` / `DeliverOne` (идемпотентна через `SELECT FOR UPDATE`, классификация CopyOK/CopyRetryAfter/CopyBlocked/CopyBadRequest с attempts-retry до `broadcast_delivery_max_attempts=3`; при CopyBlocked отмечает `users.blocked_bot_at`) / `Finalize` / `GetBroadcastCard` (с live progress-bar `▓▓░░` + счётчики sent/blocked/failed/pending + кнопка 🔄 Обновить пока running/scheduled); `AiogramBroadcastBot`-обёртка над `bot.copy_message` с `allow_paid_broadcast`, маппинг ошибок TG в `CopyResult`; TaskIQ `run_broadcast` / `deliver_one` / `finalize_broadcast` на выделенном `broadcast_broker` с глобальным Redis token-bucket `broadcast:global` 25 msg/s (1000 при `allow_paid_broadcast=True`); scheduler-тики на default broker каждую минуту: `broadcast_tick` (scan `status='scheduled' AND scheduled_at<=now() FOR UPDATE SKIP LOCKED` → running + enqueue), `finalize_running_broadcasts_tick`, `release_stale_mq_locks_tick`, `refresh_materialized_views_tick` (каждые 10 минут), `create_monthly_partitions_tick` (03:00 UTC — партиции `tracking_events` на 2 месяца вперёд); роутер `bot_status.py` на `my_chat_member` private chat помечает `blocked_bot_at` при `new_status='kicked'` и снимает при `member`/`administrator`; `PgUserSegmentReader` исключает `banned_at IS NOT NULL OR blocked_bot_at IS NOT NULL`; админ-меню `/admin` с 5 разделами: Рассылки (FSM `BroadcastFlow` с wizard шагов source→keyboard→segment→schedule→confirm), Трекинг (CRUD UTM-кодов + воронки PNG через `sendPhoto(BufferedInputFile)`), Статистика (7 дашбордов: today/week/authors/fandoms/moderators/cohort — matplotlib Agg с ленивым импортом внутри функций; today/week показывает `UsersOverview`: total/active_24h/7d/30d/blocked_bot/banned/new_today + DAU/WAU/MAU считается по `users.last_seen_at`), Фандомы (CRUD), Теги (merge-кандидаты + `MergeTagsUseCase` перепривязывает fanfic_tags и обнуляет usage_count у sources); audit-log на каждое `broadcast.create/schedule/launch/cancel/finish`, `tracking.create/deactivate`, `fandom.create/update`, `tag.merge`)
- [x] **Этап 7** — hardening (prod-ready): Observability — центральный `src/app/core/metrics.py` с метриками docs/14 (`bot_*`, `worker_*`, `broadcast_*`, `moderation_*`, `fanfics_published_total`, `chapters_published_total`, `search_*`, бизнес-Gauge'и + `outbox_oldest_pending_age_seconds`); `MetricsAiohttpSession`-обёртка aiogram-сессии для `bot_tg_api_*`; `MetricsTaskMiddleware`+`SentryTaskMiddleware` в TaskIQ-брокере; `metrics_refresh_tick` (`* * * * *`) обновляет Gauge'и глубины очередей / moderation / users / outbox-lag; `/metrics` в боте + worker/broadcast/scheduler через `prometheus_client.start_http_server` на портах 8081–8084 (env `FANTIK_WORKER_METRICS_PORT`, Docker healthchecks дёргают именно их); `src/app/core/sentry.py` с `init_sentry(component=…)` + `before_send` и `before_send_transaction` убирают `text`/`caption`/`first_name`/`last_name`/`phone`/`token`/… и ужимают `event.user` до `id`, вызывается из всех 4 entry-points + `sentry_sdk.capture_exception` в aiogram error-handler (доменные ошибки не шлём); observability-стек в compose под `--profile observability` (Prometheus 2.54 + Grafana 11.2 + Alertmanager 0.27) с datasource+dashboards provisioning; 5 дашбордов JSON в `docker/grafana/dashboards/` (bot_health / tg_api / workers / broadcast / domain); `docker/prometheus/alerts.yml` с `BotHighErrorRate` / `BotHandlerLatencyP95High` / `TGApiBadResponses` / `ModerationQueueTooDeep` / `BroadcastStalled` / `OutboxLagHigh` / `WorkerQueueBacklog`; Alertmanager Telegram-шаблон. Security — `DeleteUserCommand`/`DeleteUserUseCase` (anonymize `deleted_<sha8>` + hard-DELETE черновиков/закладок/лайков/прогресса/подписок/жалоб/уведомлений + `tracking_events.user_id=NULL` + `banned_at=now, banned_reason='self_deleted'` + audit `user.self_deleted`) с FSM `DeleteMeFlow` в `profile.py`, `display_author_nick` заменяет `deleted_*` на «Удалённый пользователь» в reader/browse/inline_search; `cover_validator.py` проверяет magic bytes JPEG (`\xFF\xD8\xFF`) / PNG (`\x89PNG\r\n\x1a\n`) + `cover_max_size_bytes=5MB`, подключён в FSM обложек `author_create.py`/`author_manage.py` до сохранения `cover_file_id`; `.github/dependabot.yml` (pip+github-actions+docker, weekly); bandit (`[tool.bandit]`) + pip-audit в CI lint job. Reliability — `stop_grace_period: 60s` на bot/worker/worker-broadcast/scheduler, 30s на deps; `signal.SIGTERM`-handler в webhook-режиме бота через `loop.add_signal_handler`; Docker healthchecks воркеров включены (через `/metrics`). Performance — `tests/load/` с `fake_tg_server.py` (aiohttp mock) + `conftest.py` (make_update_start / make_callback) + `load_start.py` (locust, p95<200ms, err<0.5%) + `load_reading.py` (p95<150ms) + `load_broadcast.py` (python-скрипт, 50k recipients, sent≥99%) + `README.md` с инструкциями; compose-profile `loadtest` поднимает `fake-tg`; Makefile — `load-start` / `load-reading` / `load-broadcast`. Operational — `scripts/smoke.sh` (healthz + readyz + /metrics всех 4 процессов, используется в CI-job `smoke` на docker compose и пост-деплой) + `make smoke`; `docs/ops/runbook.md` с per-alert действиями (BotHighErrorRate, ModerationQueueTooDeep, TGApiBadResponses, BroadcastStalled, OutboxLagHigh, WorkerQueueBacklog, Meili/PG recovery, Token rotation, monthly drill, эскалация); `scripts/backup_pg.sh` (ежедневный `pg_dump -Fc` + gzip + 30-дневная ротация, cron на host) + `scripts/restore_drill.sh` (drop/create staging, pg_restore, alembic, smoke); `docs/ops/backup.md` с cron-инструкцией и процедурой восстановления в прод. Тесты — 20 новых unit-тестов (`test_metrics_registry` / `test_sentry_scrub` / `test_display` / `test_cover_validator`), весь существующий unit-suite (315 тестов) зелёный. **Проект production-ready.**

Детали этапов — [`docs/16-roadmap.md`](docs/16-roadmap.md).

## Правила разработки

### Чего никогда не делать

- **Не импортировать** `sqlalchemy`, `aiogram`, `redis` в `src/app/domain/`. Чистый Python.
- **Не вызывать** SQL/Redis/Meilisearch напрямую из `presentation/bot/routers/`. Только через use case'ы application-слоя.
- **Не конвертировать** entities в HTML/MarkdownV2. Работать с `jsonb` напрямую.
- **Не парсить** текст broadcast'а — использовать `copy_message`.
- **Не забывать** про UTF-16 при любой работе с offset/length в MessageEntity.
- **Не делать** синхронные долгие операции в хендлере бота — уводить в TaskIQ.
- **Не писать** `--no-verify`, `--no-gpg-sign` и прочее в обход hooks.
- **Не коммитить** `.env`, секреты, токены.

### Что делать всегда

- Писать use case под каждую операцию, не оркестровать в роутере.
- Доменные события через outbox, а не напрямую в TaskIQ внутри транзакции.
- Транзакция = один use case. Событие публикуется **после** commit.
- Идемпотентность всех TaskIQ-задач (проверка статусов перед действием).
- Pydantic-валидация на границах (DTO из роутеров, конфиг).
- Типизация strict: `mypy` должен проходить.
- `ruff format` + `ruff check` перед коммитом.
- Тесты для каждого use case (unit + integration с testcontainers).

## Команды разработки

```bash
# Первый запуск
cp .env.example .env          # заполнить BOT_TOKEN, POSTGRES_PASSWORD, MEILI_MASTER_KEY, ADMIN_TG_IDS
make build
make migrate
make up

# Ежедневно
make up                        # поднять стек
make logs                      # посмотреть логи
make down                      # остановить
make test                      # прогнать тесты
make fmt                       # ruff format
make lint                      # ruff check + mypy
make migration-new m="описание"  # новая Alembic-ревизия
make db-shell                  # psql внутри контейнера
```

## Окружение

- OS: macOS (darwin 25.4.0); shell: zsh.
- Docker Desktop требуется для локального стека.
- Python 3.12 локально (опционально — в контейнере всегда).

## Если сомневаешься

1. Ищи ответ в `docs/` (структура выше).
2. Если нет — спрашивай у пользователя до реализации, не делай догадок.
3. Открытые вопросы и допущения, которые **можно поменять** — в конце [`docs/00-overview.md`](docs/00-overview.md).

## Ссылки на внешнюю документацию

- Telegram Bot API: https://core.telegram.org/bots/api
- aiogram 3 docs: https://docs.aiogram.dev/
- Meilisearch docs: https://www.meilisearch.com/docs
- TaskIQ docs: https://taskiq-python.github.io/
- SQLAlchemy 2 docs: https://docs.sqlalchemy.org/en/20/

Для актуальных версий используй **mcp context7** (`/aiogram/aiogram`, `/meilisearch/documentation`) — предпочтительнее веб-поиска.
