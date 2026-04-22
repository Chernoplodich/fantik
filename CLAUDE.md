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
- [ ] Этап 3 — читалка + пагинатор
- [ ] Этап 4 — поиск + каталог
- [ ] Этап 5 — социалка (подписки, жалобы)
- [ ] Этап 6 — админские инструменты (рассылки, статистика)
- [ ] Этап 7 — hardening (метрики, нагрузочные, безопасность)

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
