# 02 · Технологический стек и обоснование

## Рекомендованная версия стека (на момент 2026-04)

| Компонент | Версия | Роль |
|---|---|---|
| Python | 3.12+ | Язык |
| aiogram | 3.27+ | Telegram Bot framework |
| SQLAlchemy | 2.0+ (async) | ORM |
| asyncpg | latest | Асинхронный драйвер PostgreSQL |
| Alembic | latest | Миграции БД |
| PostgreSQL | 16 | Основное хранилище |
| Redis | 7 | Кэш, FSM, throttle, locks, broker |
| Meilisearch | 1.x (latest) | Полнотекстовый поиск |
| TaskIQ | latest | Распределённая очередь задач, scheduler |
| dishka | latest | DI контейнер |
| pydantic-settings | 2.x | Конфигурация из env |
| structlog | latest | Структурные логи |
| prometheus-client | latest | Метрики |
| sentry-sdk | latest | Трекинг ошибок |
| pytest + pytest-asyncio | latest | Тесты |
| testcontainers | latest | Интеграционные тесты |
| ruff | latest | Линт + форматирование |
| mypy | latest (strict) | Типы |
| uv | latest | Менеджер зависимостей |
| Docker / Compose | latest | Контейнеризация |
| nginx | stable | Reverse-proxy (для webhook) |

## Обоснования

### Python + aiogram 3
- aiogram 3 — самый зрелый Python-фреймворк для Telegram. Router-архитектура, magic filters, FSM с pluggable storage, middleware, Pydantic-модели всех типов API.
- Bot API обновляется часто; у aiogram активный релизный цикл и ранняя поддержка новых фич (paid broadcasts, Stars, custom emoji).
- Python сильно упрощает работу с `MessageEntities`: типы и конвертеры из коробки.
- I/O-bound нагрузка (TG API + БД + Redis + Meili) обрабатывается asyncio без выхода за пределы GIL.
- Найм Python-разработчиков и наличие готовых библиотек (aiogram-toolkit, aiogram-dialog) сокращают time-to-market.

### PostgreSQL 16
- Зрелая ACID-БД с JSONB, массивами, партиционированием, оконными функциями, `FOR UPDATE SKIP LOCKED`.
- Полнотекстовый поиск с поддержкой русской морфологии (`russian` text search configuration) как резерв, если Meilisearch недоступен.
- `pg_trgm` для fuzzy-поиска по никам и заголовкам.
- BRIN-индексы для дешёвой индексации time-series таблиц (`tracking_events`, `audit_log`).
- Логическая репликация и streaming — простой путь к read-replica для отчётов.

### Redis 7
- Нативный FSM storage в aiogram (`RedisStorage`) с TTL.
- Брокер и result-backend для TaskIQ.
- Distributed token-bucket для anti-flood и broadcast rate-limit.
- Distributed locks через `SET NX EX` для throttle прогресса чтения.
- Кэш: горячие страницы, роли пользователей, инлайн-результаты поиска.

### Meilisearch
- Sub-50ms latency, typo-tolerance, фасетный поиск, готовая токенизация русского через Charabia.
- Проще в операционке, чем Elasticsearch: один бинарь, один процесс, несколько МБ памяти на индекс нашего размера.
- Нативные `filterableAttributes`, `sortableAttributes`, кастомные `rankingRules` — всё, что нужно для фасетов (фандом, возрастной рейтинг, теги) без SQL.
- Альтернативы: Typesense (аналог), Elasticsearch/OpenSearch (тяжелее), Sonic (примитивнее, без фасетов).

### TaskIQ
- Asyncio-нативная очередь с API, похожим на Celery.
- Декларативные задачи `@broker.task`, планировщик `TaskiqScheduler` для отложенных/cron задач.
- Работает с Redis broker + result backend, что исключает новый компонент (RabbitMQ).
- По бенчмаркам 10× быстрее Python-RQ и ARQ, сопоставим с Celery без её sync-боли.
- Альтернативы: Celery (sync-ориентирован, сложнее интегрируется с asyncio, но максимально зрелый), ARQ (проще, но чувствуется недостаток features).

### SQLAlchemy 2 + asyncpg + Alembic
- SQLAlchemy 2.0 — mapped_column, async session, typed queries; современная и стабильная.
- `asyncpg` — лидер по производительности среди async-драйверов PostgreSQL.
- Alembic — стандарт миграций; генерация из моделей + ручные правки для партиционирования.

### dishka
- Async-first, хорошо ложится на aiogram (официальная интеграция через middleware).
- Scope-based (app / request / session) — корректно изолирует сессии БД.
- Явные провайдеры, без магии и глобальных импортов.

### structlog + prometheus-client + Sentry
- structlog — JSON-логи для ELK/Loki, context binding с apyте пользователя/апдейта.
- prometheus-client — экспорт метрик по `/metrics`, стандартный протокол для Grafana/Prometheus.
- Sentry — трейсы ошибок с контекстом пользователя.

### Тесты: pytest + testcontainers
- pytest — де-факто стандарт.
- testcontainers поднимает реальные PG/Redis/Meili в контейнерах для интеграционных тестов — исключает проблемы "на моках всё работало".
- pytest-asyncio для async-тестов.
- hypothesis (опционально) для property-based тестов на пагинатор.

### ruff + mypy
- ruff: супербыстрый линтер+форматтер (replace для flake8/black/isort).
- mypy в strict-режиме + Pydantic v2 даёт типобезопасность на стыках слоёв.

### uv (или poetry)
- `uv` — молниеносный менеджер зависимостей (pip+pip-tools+virtualenv replacement), детерминированный lock.
- Если команде привычнее `poetry` — допустимо; функционально эквивалентно.

## Альтернативы, которые рассматривались, и почему отказано

| Вариант | Почему нет |
|---|---|
| **Go + telebot/telego** | Экосистема TG в Go уступает aiogram: нет готовых FSM, парсеров entities, middleware; всё руками. Прирост производительности нивелируется лимитами Telegram (30 msg/s). |
| **Node.js + grammY** | grammY — очень хороший фреймворк, но комьюнити и библиотеки для тяжёлой обработки entities и интеграции с PG/Meili сильнее в Python. |
| **MongoDB** | Реляционные связи (fandom→fanfic, tags m:n, moderation queue с FOR UPDATE) гораздо удобнее в PostgreSQL. JSONB в PG закрывает кейсы, где MongoDB была бы преимуществом. |
| **Elasticsearch** | Тяжелее в эксплуатации, больше памяти, сложнее настраивать русскую морфологию. Meilisearch достаточен; если упрёмся — портируем индекс. |
| **Celery** | Sync-first; нужна интеграция через `eventlet`/`gevent`, что усложняет debugging. TaskIQ async-нативен. |
| **RabbitMQ как брокер** | Лишний компонент; Redis вытягивает объёмы задач проекта с запасом. |
| **SQLite** | Не подходит для concurrent writes нашего уровня; нет `FOR UPDATE SKIP LOCKED` с нужными гарантиями. |
| **Monolith без выделения воркеров** | Долгие задачи (рассылки на 100к) заблокируют ответы на апдейты. |

## Точки расширения

### Платежи (Telegram Stars / Payments API)
Добавляется:
- Модуль `domain/payments/` с сущностями `Invoice`, `Subscription`, `StarTransaction`.
- Use case'ы `CreateInvoice`, `HandlePaymentUpdate`, `CheckSubscription`.
- Хэндлеры `pre_checkout_query`, `successful_payment`.
- Опционально: `allow_paid_broadcast=True` в рассылках для > 30 msg/s.

Без переписывания существующего кода.

### Mini App (Telegram WebApp)
- Отдельный FastAPI-сервис (`presentation/miniapp/`).
- Авторизация через `initData` (Bot API WebApp validation).
- Переиспользует application-слой (те же use case'ы, DI).
- Отдельный контейнер в compose (`miniapp`), отдельный Nginx-маршрут.

### Семантический поиск
- Добавить `infrastructure/search/vector.py` (pgvector в той же PG или Qdrant).
- Эмбеддинги через OpenAI/локальная модель → сохраняем в `fanfics_embeddings(fic_id, embedding)`.
- `application/search/hybrid.py` объединяет Meilisearch + vector-поиск с реранжированием.

### Elasticsearch / OpenSearch
Если объём превысит лимиты Meilisearch (> 1M документов, сложные агрегации):
- Интерфейс `ISearchIndexer` + `ISearchQuery` уже есть.
- Новая реализация `ElasticsearchSearchAdapter`.
- Переключается через настройку `SEARCH_BACKEND=meili|elasticsearch`.

### Webhook-режим
- В `bot_factory.py` флаг `run_mode=polling|webhook`.
- В `docker-compose.prod.yml` включается `nginx` + TLS.
- URL: `/webhook/<token_sha256>` чтобы скрыть токен.

### Horizontal scale worker
- worker и worker-broadcast масштабируются `deploy: replicas: N` в Compose / `replicas: N` в k8s.
- Задачи идемпотентны (проверка по `broadcast_deliveries.status`), дубли исключены.

### Managed БД/кэш
- Все адреса в env → меняем `POSTGRES_DSN`, `REDIS_URL`, `MEILI_URL` на managed.
- Volumes `postgres_data`/`redis_data`/`meili_data` становятся не нужны в Compose.

## Сводные причины «быть готовым к росту»

1. Слой с портами → замена адаптера без правок бизнес-логики.
2. Отдельные процессы по ролям → независимое масштабирование.
3. Доменные события → легко добавить новых подписчиков.
4. Нормализованная БД с партиционированием и BRIN → не переписываем схему при росте.
5. Observability с первого дня → видим узкое место, когда оно появится.
