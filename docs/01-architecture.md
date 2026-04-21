# 01 · Архитектура

## Принципы

- **Clean / Layered Architecture** — зависимости направлены внутрь: `presentation → application → domain`; `infrastructure` реализует порты `application`.
- **Domain-Driven Design** — модули организованы по бизнес-доменам (users, fanfics, moderation, broadcasts, tracking, search), а не по техническим слоям.
- **Repository + Unit of Work** — доступ к БД через репозитории с транзакционной границей (`UoW`).
- **Dependency Injection** — через контейнер (рекомендуется [`dishka`](https://github.com/reagento/dishka) — async-first, нативный с aiogram).
- **Event-driven внутри монолита** — доменные события (`FanficApproved`, `ChapterUpdated`, `UserRegistered`) публикуются в шину и подписчики (индексация, нотификации, аналитика) обрабатывают их через TaskIQ-задачи.
- **Stateless bot** — любое состояние между сообщениями (FSM, throttle, locks) живёт в Redis; контейнер бота можно масштабировать и перезапускать без потерь.
- **Fail-fast + graceful degradation** — при отказе Meilisearch переход на PG FTS; при отказе Redis — временно без throttling; бот продолжает отвечать.

## Высокоуровневая схема

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                            Telegram Bot API / Updates                         │
└───────────────────────▲──────────────────────────────────────▲────────────────┘
                        │ polling/webhook                       │ sendMessage / copyMessage
                        │                                        │
          ┌─────────────┴─────────────┐            ┌─────────────┴─────────────┐
          │         bot (aiogram)     │            │       worker (TaskIQ)     │
          │  routers · middlewares    │            │   indexing · notify ·     │
          │  filters · FSM · keyboards│            │   repaginate              │
          └──┬─────────┬──────────┬───┘            └───────────────┬───────────┘
             │         │          │                                │
             │         │          │     ┌─────────────────────┐   │
             │         │          └────▶│   worker-broadcast  │◀──┘
             │         │                │  global token bucket│
             │         │                └───────────┬─────────┘
             │         │                            │
             ▼         ▼                            ▼
        ┌────────┐ ┌────────┐              ┌─────────────────┐
        │  PG    │ │ Redis  │◀─────────────│    scheduler    │
        │        │ │ FSM +  │              │   (TaskIQ)      │
        │        │ │ cache  │              │  due tasks      │
        └────────┘ └────────┘              └─────────────────┘
             │
             └──▶ events ──▶ Meilisearch (index)
```

## Процессы (отдельные контейнеры)

### 1. `bot`
Получает апдейты, маршрутизирует в хендлер, быстро отвечает пользователю. **Запрещено**: синхронная долгая работа (рассылки, индексация больших объёмов). Всё тяжёлое — в очередь.

### 2. `worker` (TaskIQ)
Обработчик фоновых задач: индексация в Meilisearch, репагинация глав, отправка уведомлений, агрегация статистики. Масштабируется горизонтально, задачи идемпотентны.

### 3. `worker-broadcast`
Выделенный пул воркеров для отправки рассылок с **глобальным token-bucket в Redis** на 25 msg/s (буфер от лимита Telegram 30 msg/s). Отделён от обычного воркера, чтобы разовая рассылка 100k сообщений не блокировала уведомления подписчиков.

### 4. `scheduler` (TaskIQ scheduler)
Планирует отложенные задачи: рассылки по расписанию, ежечасные/ежесуточные агрегации, чистку старых FSM-ключей, ребилд индекса, периодические напоминания.

## Слои приложения

### Domain (`src/app/domain/`)
Чистый Python без инфраструктуры. Содержит:

- **Entities** — бизнес-объекты с идентичностью (`User`, `Fanfic`, `Chapter`, `ModerationCase`).
- **Value Objects** — без идентичности, иммутабельны (`AuthorNick`, `FandomSlug`, `AgeRating`, `EntityOffset`).
- **Domain Services** — логика, не принадлежащая одной сущности (`ChapterPaginator`, `EntityValidator`, `TagMerger`).
- **Domain Events** — `FanficSubmitted`, `FanficApproved`, `FanficRejected`, `ChapterPublished`, `UserSubscribed`.

Этот слой можно запускать без БД, Redis, Telegram — для быстрых unit-тестов.

### Application (`src/app/application/`)
Оркестрация use case'ов. Содержит:

- **Use cases / Interactors** — один класс на операцию: `CreateDraftUseCase`, `SubmitForReviewUseCase`, `ApproveFanficUseCase`, `PaginateChapterUseCase`, `StartBroadcastUseCase`.
- **Ports (Protocol / ABC)** — интерфейсы `IFanficRepository`, `ISearchIndexer`, `INotifier`, `IBroadcastQueue`, `ITelegramGateway`.
- **DTO** — данные между presentation и application.

Use case — это единица транзакции; вход — DTO, выход — DTO или доменное событие.

### Infrastructure (`src/app/infrastructure/`)
Реализация портов application и адаптеров к внешним системам:

- **db/** — SQLAlchemy-модели, репозитории, Unit of Work.
- **redis/** — кэш, FSM storage, token-bucket, distributed locks.
- **search/** — Meilisearch client + индексатор.
- **tasks/** — TaskIQ broker, задачи (`index_fanfic`, `send_broadcast_message`, `repaginate_chapter`, `notify_subscribers`).
- **telegram/** — фабрика `Bot`, утилиты парсинга entities, валидация пермишенов чатов.

### Presentation (`src/app/presentation/bot/`)
Aiogram 3: `Dispatcher`, `Router`'ы, хендлеры, middleware, фильтры, клавиатуры, FSM-состояния. Тонкий слой — только преобразование апдейта в DTO и вызов use case'а.

## Потоки данных

### Публикация фанфика → модерация → индексация

```
User → bot → FSM(create_fanfic) → repo.save_draft()
User → bot → submit_for_review.UseCase
        ├── fanfics.set_status(pending)
        ├── moderation_queue.enqueue()
        └── publish DomainEvent(FanficSubmitted)
                ↓
            notifier.send("Ваша работа отправлена на модерацию")

Moderator → bot → approve_fanfic.UseCase
        ├── fanfics.set_status(approved)
        ├── moderation_queue.decide(approved)
        ├── publish DomainEvent(FanficApproved)
        └── commit UoW
                ↓
            subscriber handlers (TaskIQ):
              · index_fanfic(fic_id) → Meilisearch
              · notify_author(fic_id) → sendMessage
              · notify_subscribers(author_id, fic_id) → fanout
              · repaginate_all_chapters(fic_id) → chapter_pages
```

### Рассылка

```
Admin → bot → FSM(broadcast) → save source message + keyboard + segment
Admin → bot → launch / schedule
        ↓
   scheduler: TaskIQ task run_broadcast(broadcast_id) at scheduled_at
        ↓
   run_broadcast:
        ├── resolve segment → SELECT users (paged 1000)
        └── for each batch: enqueue send_one(bc_id, user_id) × N

   worker-broadcast:
        ├── global_rate_limiter.acquire()
        └── bot.copy_message(user.tg_id, source_chat, source_msg, reply_markup)
                ↓
            broadcast_deliveries.set_status(sent|failed|blocked)
```

### Чтение

```
User → bot → open_fic → sendPhoto(cover, "Читать")
User → bot → read_chapter(fic, ch=1)
        ├── repo.get_page(chapter_id, page=1) — сначала Redis, затем PG
        │   └── если нет → PaginateChapterUseCase(ленивое построение + сохранение)
        ├── editMessageText(text, entities=[...], reply_markup=navigation)
        └── throttled: save_reading_progress(user, fic, ch, page)
```

## Domain events и обработчики

Список событий → подписчиков. Реализация — через локальный in-memory event bus при коммите UoW + TaskIQ для асинхронных:

| Событие | Синхронные обработчики | TaskIQ-подписчики |
|---|---|---|
| `UserRegistered` | Метрика `users_total`+1 | `record_tracking_event(user_id, 'register')` |
| `FanficSubmitted` | — | `notify_moderators()` |
| `FanficApproved` | — | `index_fanfic()`, `notify_author()`, `notify_subscribers()`, `record_tracking_event` |
| `FanficRejected` | — | `notify_author_with_reason()` |
| `ChapterPublished` | — | `repaginate_chapter()`, `notify_subscribers()` |
| `UserSubscribedToAuthor` | — | `update_author_subscribers_count_cache()` |
| `BroadcastScheduled` | — | через scheduler, задача запустится в `scheduled_at` |

## Границы транзакций

- Один use case = одна транзакция UoW.
- Доменные события собираются в буфер UoW и публикуются **после** успешного коммита.
- Если событие должно запуститься гарантированно (например, индексация после approve), используется **outbox**-паттерн: в той же транзакции запись в таблицу `outbox`, отдельный воркер публикует в TaskIQ. Это предохраняет от потери событий при падении процесса между commit и publish.

## Dependency Injection

`dishka` предоставляет scope-based DI, совместимый с aiogram через middleware. Три скоупа:

- **App scope** — singleton'ы: `Settings`, `Bot`, `SearchClient`, `RedisPool`, `AsyncEngine`, `TaskiqBroker`.
- **Request scope** — на один апдейт/задачу: `AsyncSession`, `UnitOfWork`, `Repositories`, `UseCases`.
- **Request from TaskIQ** — то же, но от задачи, не от апдейта.

Это изолирует сессии БД между апдейтами, исключает утечки подключений.

## Чего избегаем

- **Фат-контроллеров** — хендлер не должен знать про SQL. Он вызывает use case.
- **Круговых импортов** — `domain` ничего не знает про SQLAlchemy/aiogram; `application` — только про порты; `infrastructure` — реализует порты.
- **Глобального состояния** — никаких module-level singleton'ов, только через DI.
- **Синхронных операций в хендлере** — любое > 100 мс действие уходит в воркер.
- **"God-tables"** — нормализация и партиционирование с первого дня там, где это оправдано.

## Точки расширения

- **Платежи** — новый модуль `domain/payments/` + `application/payments/` + router `payments.py`. Точка инъекции — кнопка в меню фика, проверка на `has_active_subscription`.
- **Mini App** — добавляется `presentation/miniapp/` (FastAPI за `aiohttp`-gateway'ем aiogram) и отдельный deploy-unit.
- **Семантический поиск** — добавить `infrastructure/search/vector.py` (pgvector или Qdrant), объединять результаты в `application/search/hybrid.py`.
- **Комментарии** — новый модуль, в БД таблица `comments`, при публикации комментария — domain event.

## Дальше

- Стек и обоснование — [`02-stack-and-rationale.md`](02-stack-and-rationale.md).
- Структура кода — [`04-modules.md`](04-modules.md).
- Диаграммы — [`diagrams/`](diagrams/).
