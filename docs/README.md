# Fantik — проектная документация

Телеграм-бот для создания и чтения фанфиков с модерацией, поиском, рассылками и трекингом.

## Чтение документации

Начни с [`00-overview.md`](00-overview.md) — общий обзор, роли, допущения, глоссарий и навигация.

Если нужно быстро понять конкретный аспект — переходи к тематическому файлу.

| Тема | Файл |
|---|---|
| Обзор, цели, роли, допущения | [`00-overview.md`](00-overview.md) |
| Архитектура и потоки | [`01-architecture.md`](01-architecture.md) |
| Tech stack с обоснованием | [`02-stack-and-rationale.md`](02-stack-and-rationale.md) |
| Схема БД PostgreSQL | [`03-data-model.md`](03-data-model.md) |
| Структура кода и модули | [`04-modules.md`](04-modules.md) |
| Пользовательские сценарии | [`05-user-flows.md`](05-user-flows.md) |
| Админка и модерация | [`06-admin-and-moderation.md`](06-admin-and-moderation.md) |
| Рассылки (ключевая фича) | [`07-broadcast-system.md`](07-broadcast-system.md) |
| Поиск (Meilisearch) | [`08-search-design.md`](08-search-design.md) |
| Читалка и пагинатор | [`09-reader-pagination.md`](09-reader-pagination.md) |
| Трекинг и аналитика | [`10-tracking-analytics.md`](10-tracking-analytics.md) |
| Масштабирование, производительность | [`11-scalability-performance.md`](11-scalability-performance.md) |
| Безопасность, приватность | [`12-security-privacy.md`](12-security-privacy.md) |
| Docker, CI/CD, операционка | [`13-deployment-docker.md`](13-deployment-docker.md) |
| Логи, метрики, алерты | [`14-observability.md`](14-observability.md) |
| Тестирование | [`15-testing.md`](15-testing.md) |
| Дорожная карта | [`16-roadmap.md`](16-roadmap.md) |
| Диаграммы | [`diagrams/`](diagrams/) |

## Tech stack (short)

- **Python 3.12** + **aiogram 3** (Telegram bot framework)
- **PostgreSQL 16** + **SQLAlchemy 2 (async)** + **asyncpg** + **Alembic**
- **Redis 7** (FSM, кэш, rate-limit, TaskIQ broker)
- **Meilisearch** (полнотекст + фасеты)
- **TaskIQ** (asyncio-native queue, scheduler)
- **dishka** (DI)
- **structlog** + **prometheus-client** + **Sentry**
- **Docker** + **docker-compose**
- Обоснование — в [`02-stack-and-rationale.md`](02-stack-and-rationale.md).

## Основные архитектурные решения

1. **Broadcast через `copyMessage`** — админ пересылает/пишет шаблон боту, бот сохраняет `source_chat_id+message_id` и отправляет копию каждому получателю. Сохраняется **любое** форматирование, медиа, custom/animated emoji. Клавиатура задаётся отдельно.
2. **Entities хранятся как JSON Telegram API** — никаких HTML/Markdown конверсий.
3. **UTF-16 offsets в пагинаторе** — entities измеряются в UTF-16 units, не code points.
4. **Materialized страницы в `chapter_pages`** — построены воркером при публикации, кешируются в Redis при чтении.
5. **`SELECT FOR UPDATE SKIP LOCKED`** для очереди модерации — никаких гонок.
6. **Разделённые процессы**: `bot`, `worker`, `worker-broadcast`, `scheduler` — рассылки не блокируют нотификации.
7. **Event-driven индексация в Meili** — публикация мгновенная, индексация — в фоне.
8. **Любая правка approved-фика → обратно в `pending`** — единое правило, никакой специальной политики «минорных» правок.

## Как начать разработку

После одобрения этой документации:

1. `cp .env.example .env` — заполнить `BOT_TOKEN`, `POSTGRES_PASSWORD`, `MEILI_MASTER_KEY`, `ADMIN_TG_IDS`.
2. `make build`
3. `make migrate`
4. `make up`
5. `/start` в Telegram → проверка.

Этапы реализации — в [`16-roadmap.md`](16-roadmap.md). Начинаем с Этапа 0 (скелет проекта).

## Статус

Документация — **v1**, создана после сбора требований и research. Готова к реализации.

Открытые вопросы / допущения, которые легко скорректировать до кода — в конце [`00-overview.md`](00-overview.md).
