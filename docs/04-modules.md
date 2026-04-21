# 04 · Модули и структура кода

## Дерево пакетов

```
src/
└── app/
    ├── __init__.py
    ├── core/
    │   ├── config.py              # pydantic-settings: BotSettings, DBSettings, RedisSettings, MeiliSettings, TaskiqSettings
    │   ├── logging.py             # structlog setup, JSON renderer
    │   ├── errors.py              # базовые DomainError, ApplicationError, InfrastructureError
    │   ├── di/
    │   │   ├── __init__.py
    │   │   ├── container.py       # dishka providers
    │   │   └── scopes.py
    │   └── clock.py               # абстракция времени для тестов (FrozenClock)
    │
    ├── domain/                    # pure Python, без aiogram/sqlalchemy
    │   ├── shared/
    │   │   ├── events.py          # базовый класс DomainEvent
    │   │   └── types.py           # NewType для UserId, FicId, ChapterId
    │   ├── users/
    │   │   ├── entities.py        # User
    │   │   ├── value_objects.py   # AuthorNick, Role
    │   │   ├── events.py          # UserRegistered, UserBanned, UserRoleChanged
    │   │   └── exceptions.py
    │   ├── fanfics/
    │   │   ├── entities.py        # Fanfic, Chapter, ChapterPage
    │   │   ├── value_objects.py   # AgeRating, FandomRef, MessageEntity, FicStatus
    │   │   ├── services/
    │   │   │   ├── paginator.py       # ChapterPaginator — чистый
    │   │   │   ├── entity_validator.py # запрет опасных URL-entities
    │   │   │   └── tag_normalizer.py
    │   │   ├── events.py          # FanficSubmitted, FanficApproved, FanficRejected, ChapterPublished
    │   │   └── exceptions.py
    │   ├── moderation/
    │   │   ├── entities.py        # ModerationCase
    │   │   ├── value_objects.py   # RejectionReason
    │   │   ├── policies.py        # revise/resubmit policy
    │   │   └── events.py
    │   ├── broadcasts/
    │   │   ├── entities.py        # Broadcast, SegmentSpec, DeliveryStatus
    │   │   ├── segment_resolver.py # чистая логика интерпретации segment_spec
    │   │   └── events.py
    │   ├── tracking/
    │   │   ├── entities.py        # TrackingCode, TrackingEvent
    │   │   └── events.py
    │   └── search/
    │       └── value_objects.py   # SearchQuery, SearchFilters, FacetValues
    │
    ├── application/
    │   ├── shared/
    │   │   ├── ports/             # общие порты (UnitOfWork, EventBus, Clock)
    │   │   └── dto/
    │   ├── users/
    │   │   ├── ports.py           # IUserRepository, IRolesCache
    │   │   ├── register_user.py   # RegisterUserUseCase
    │   │   ├── set_author_nick.py
    │   │   ├── change_role.py
    │   │   └── ban_user.py
    │   ├── fanfics/
    │   │   ├── ports.py           # IFanficRepository, IChapterRepository, ICoverStorage
    │   │   ├── create_draft.py
    │   │   ├── update_fanfic.py
    │   │   ├── add_chapter.py
    │   │   ├── update_chapter.py
    │   │   ├── delete_chapter.py
    │   │   ├── submit_for_review.py
    │   │   ├── cancel_submission.py
    │   │   ├── archive_fanfic.py
    │   │   └── revise_after_rejection.py
    │   ├── moderation/
    │   │   ├── ports.py           # IModerationRepository, IReasonRepository
    │   │   ├── pick_next.py        # take next from queue with lock
    │   │   ├── approve.py
    │   │   ├── reject.py
    │   │   └── release_stale_locks.py
    │   ├── reading/
    │   │   ├── ports.py           # IPagesRepository, IProgressRepository
    │   │   ├── open_fanfic.py
    │   │   ├── paginate_chapter.py # lazy-build + cache
    │   │   ├── read_page.py
    │   │   ├── save_progress.py
    │   │   ├── toggle_like.py
    │   │   └── toggle_bookmark.py
    │   ├── search/
    │   │   ├── ports.py           # ISearchIndexer, ISearchQuery, IFacetProvider
    │   │   ├── index_fanfic.py
    │   │   ├── delete_from_index.py
    │   │   ├── search.py           # высокоуровневый поиск
    │   │   └── suggest.py          # автодополнения (tags, fandoms)
    │   ├── broadcasts/
    │   │   ├── ports.py           # IBroadcastRepository, IDeliveryQueue, IBotGateway
    │   │   ├── create_draft.py
    │   │   ├── set_keyboard.py
    │   │   ├── set_segment.py
    │   │   ├── schedule.py
    │   │   ├── launch.py
    │   │   ├── cancel.py
    │   │   ├── enumerate_recipients.py
    │   │   └── deliver_one.py      # вызывается в worker-broadcast
    │   ├── tracking/
    │   │   ├── ports.py
    │   │   ├── create_code.py
    │   │   ├── record_event.py
    │   │   └── query_funnel.py
    │   ├── subscriptions/
    │   │   ├── ports.py
    │   │   ├── subscribe.py
    │   │   ├── unsubscribe.py
    │   │   └── notify_subscribers.py
    │   ├── reports/
    │   │   ├── ports.py
    │   │   ├── create_report.py
    │   │   └── handle_report.py
    │   └── admin/
    │       ├── ports.py            # статистика
    │       ├── daily_summary.py
    │       ├── moderator_load.py
    │       └── top_fandoms.py
    │
    ├── infrastructure/
    │   ├── db/
    │   │   ├── engine.py           # async engine factory
    │   │   ├── session.py          # session factory + sessionmaker
    │   │   ├── models/             # SQLAlchemy: user.py, fanfic.py, chapter.py, ...
    │   │   ├── mappers/            # преобразование доменной сущности ↔ ORM-модель
    │   │   ├── repositories/
    │   │   │   ├── users.py
    │   │   │   ├── fanfics.py
    │   │   │   ├── chapters.py
    │   │   │   ├── moderation.py
    │   │   │   ├── tags.py
    │   │   │   ├── bookmarks_likes.py
    │   │   │   ├── subscriptions.py
    │   │   │   ├── broadcasts.py
    │   │   │   ├── tracking.py
    │   │   │   ├── reports.py
    │   │   │   └── outbox.py
    │   │   ├── unit_of_work.py
    │   │   └── queries/            # read-only сложные запросы (аналитика)
    │   ├── redis/
    │   │   ├── pool.py
    │   │   ├── cache.py
    │   │   ├── fsm_storage.py      # обёртка над RedisStorage
    │   │   ├── token_bucket.py     # rate-limit primitive (Lua script)
    │   │   ├── locks.py            # distributed lock
    │   │   └── progress_throttle.py
    │   ├── search/
    │   │   ├── meili_client.py
    │   │   ├── indexer.py
    │   │   ├── query.py
    │   │   ├── settings_bootstrap.py # создаёт/обновляет настройки индекса при старте
    │   │   └── fallback_pg.py       # fallback к PG FTS
    │   ├── tasks/
    │   │   ├── broker.py            # TaskiqBroker setup
    │   │   ├── scheduler.py
    │   │   ├── registry.py          # регистрация задач
    │   │   ├── indexing.py          # index_fanfic, delete_fanfic_from_index
    │   │   ├── repagination.py      # repaginate_chapter
    │   │   ├── broadcast.py         # run_broadcast, deliver_message
    │   │   ├── notifications.py     # deliver_notification
    │   │   ├── analytics.py         # refresh_materialized_views, compute_daily_metrics
    │   │   ├── maintenance.py       # release_stale_mq_locks, create_monthly_partitions, cleanup_expired_fsm
    │   │   └── outbox.py            # outbox dispatcher
    │   ├── telegram/
    │   │   ├── bot_factory.py
    │   │   ├── entity_utils.py      # split/shift entities, UTF-16 math
    │   │   ├── copy_message.py      # обёртка с retry/error mapping
    │   │   ├── message_builder.py   # склейка текст + entities + reply_markup
    │   │   ├── keyboards_from_json.py
    │   │   └── api_errors.py        # классификация ошибок TG API
    │   └── observability/
    │       ├── metrics.py           # prometheus-client registry
    │       ├── tracing.py
    │       └── sentry.py
    │
    └── presentation/
        ├── bot/
        │   ├── main.py              # entrypoint: сборка Dispatcher, регистрация роутеров
        │   ├── di_middleware.py     # подключение dishka
        │   ├── middlewares/
        │   │   ├── user_upsert.py   # создаёт/обновляет users на каждом апдейте
        │   │   ├── throttle.py      # token bucket per user
        │   │   ├── role.py          # подгружает роль из Redis-кэша
        │   │   ├── i18n.py
        │   │   ├── logging.py
        │   │   └── metrics.py
        │   ├── filters/
        │   │   ├── role.py          # IsModerator, IsAdmin
        │   │   ├── author.py        # HasAuthorNick
        │   │   └── callback.py      # CallbackData filters
        │   ├── fsm/
        │   │   ├── states/
        │   │   │   ├── create_fanfic.py
        │   │   │   ├── edit_fanfic.py
        │   │   │   ├── add_chapter.py
        │   │   │   ├── revise_after_rejection.py
        │   │   │   ├── broadcast.py
        │   │   │   └── admin_tag_merge.py
        │   │   └── callback_data.py # CallbackData classes
        │   ├── keyboards/
        │   │   ├── main_menu.py
        │   │   ├── reader.py        # ◀ ▶ 📑 ❤️ ⚠️
        │   │   ├── filters.py       # фасеты: фандом/рейтинг/теги
        │   │   ├── moderation.py
        │   │   ├── broadcast_wizard.py
        │   │   └── profile.py
        │   ├── texts/                # шаблоны сообщений (i18n ready)
        │   │   └── ru.py
        │   ├── routers/
        │   │   ├── start.py
        │   │   ├── onboarding.py
        │   │   ├── profile.py
        │   │   ├── browse.py
        │   │   ├── reader.py
        │   │   ├── author_create.py
        │   │   ├── author_manage.py
        │   │   ├── moderation.py
        │   │   ├── reports.py
        │   │   ├── admin_stats.py
        │   │   ├── admin_broadcast.py
        │   │   ├── admin_tracking.py
        │   │   ├── admin_tags.py
        │   │   ├── admin_fandoms.py
        │   │   └── errors.py         # global error handler
        │   └── inline/
        │       └── search.py         # @bot <query>
        │
        └── worker/
            ├── main.py               # entrypoint TaskIQ worker
            ├── broadcast_main.py     # entrypoint worker-broadcast (separate command)
            └── scheduler_main.py     # entrypoint scheduler
```

## Ответственности модулей

### `core`
Общие инфраструктурные вещи: конфиг, логирование, DI, абстракция времени. Не содержит бизнес-логики.

### `domain`
Чистый Python. Правило: `from sqlalchemy ...`, `from aiogram ...`, `from redis ...` — **запрещены**. Только `dataclasses`/Pydantic.

### `application`
Оркестрация доменной логики. Знает о портах (Protocol/ABC), но не о реализациях.

### `infrastructure`
Реализует порты. Точки интеграции с внешним миром.

### `presentation/bot`
Тонкий Telegram-слой. Хендлер:
1. Достаёт из апдейта параметры.
2. Собирает DTO.
3. Вызывает use case.
4. По результату рендерит ответ (`send_message` / `edit_message` / `answer_callback_query`).

Логику принципиально не пишем — она живёт в `application` и `domain`.

### `presentation/worker`
Entrypoint'ы для TaskIQ-процессов. Задачи определены в `infrastructure/tasks/`, здесь только импорт и запуск.

## Основные контракты (Protocol)

Пример для `fanfics`:

```python
# application/fanfics/ports.py
from typing import Protocol
from app.domain.fanfics.entities import Fanfic, Chapter

class IFanficRepository(Protocol):
    async def get(self, fic_id: int) -> Fanfic | None: ...
    async def get_for_update(self, fic_id: int) -> Fanfic | None: ...
    async def list_by_author(self, author_id: int, *, status: str | None = None) -> list[Fanfic]: ...
    async def save(self, fic: Fanfic) -> None: ...
    async def delete(self, fic_id: int) -> None: ...

class IChapterRepository(Protocol):
    async def get(self, chapter_id: int) -> Chapter | None: ...
    async def list_by_fic(self, fic_id: int) -> list[Chapter]: ...
    async def save(self, chapter: Chapter) -> None: ...
    async def delete(self, chapter_id: int) -> None: ...

class ICoverStorage(Protocol):
    async def validate_and_store(self, tg_file_id: str) -> tuple[str, str]: ...
```

## Use case пример

```python
# application/fanfics/submit_for_review.py
from dataclasses import dataclass
from app.application.shared.ports import IUnitOfWork
from app.application.fanfics.ports import IFanficRepository
from app.application.moderation.ports import IModerationRepository
from app.domain.fanfics.events import FanficSubmitted
from app.domain.fanfics.exceptions import FanficNotEligibleError

@dataclass
class SubmitForReviewCommand:
    fic_id: int
    author_id: int

@dataclass
class SubmitForReviewResult:
    fic_id: int
    queue_id: int

class SubmitForReviewUseCase:
    def __init__(
        self,
        uow: IUnitOfWork,
        fics: IFanficRepository,
        mod: IModerationRepository,
    ) -> None:
        self._uow = uow
        self._fics = fics
        self._mod = mod

    async def __call__(self, cmd: SubmitForReviewCommand) -> SubmitForReviewResult:
        async with self._uow:
            fic = await self._fics.get_for_update(cmd.fic_id)
            if fic is None or fic.author_id != cmd.author_id:
                raise FanficNotEligibleError("no such fic / not yours")
            fic.submit_for_review()           # domain method: validates + raises event
            await self._fics.save(fic)
            queue_id = await self._mod.enqueue(fic)
            self._uow.record_events(fic.pull_events())  # will emit after commit
            await self._uow.commit()
        return SubmitForReviewResult(fic_id=fic.id, queue_id=queue_id)
```

## Роутер пример

```python
# presentation/bot/routers/author_manage.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import inject, FromDishka
from app.application.fanfics.submit_for_review import (
    SubmitForReviewUseCase, SubmitForReviewCommand,
)
from app.presentation.bot.fsm.callback_data import FicAction

router = Router()

@router.callback_query(FicAction.filter(F.action == "submit"))
@inject
async def submit_handler(
    cb: CallbackQuery,
    callback_data: FicAction,
    use_case: FromDishka[SubmitForReviewUseCase],
) -> None:
    try:
        result = await use_case(SubmitForReviewCommand(
            fic_id=callback_data.fic_id,
            author_id=cb.from_user.id,
        ))
    except Exception:
        await cb.answer("Не получилось отправить. Попробуй ещё раз.", show_alert=True)
        return
    await cb.message.edit_text(
        f"Работа №{result.fic_id} в очереди на модерацию. Как только решат — пришлём."
    )
    await cb.answer()
```

## Правила кросс-слойного импорта

```
presentation → application (allowed)
presentation → infrastructure (forbidden, only через DI)
application → domain (allowed)
application → infrastructure (forbidden, only through ports)
infrastructure → domain (allowed: для мапперов)
infrastructure → application (allowed: реализует порты из application)
domain → * (forbidden)
```

Проверка на CI: `import-linter` с конфигом `importlinter.cfg`.

## Сводные use-case'ы по модулям

| Модуль | Use cases |
|---|---|
| users | RegisterUser, SetAuthorNick, ChangeRole, BanUser, UnbanUser, UpdateProfile |
| fanfics | CreateDraft, UpdateFanfic, AddChapter, UpdateChapter, DeleteChapter, SubmitForReview, CancelSubmission, ReviseAfterRejection, ArchiveFanfic |
| moderation | PickNext, Approve, Reject, ReleaseStaleLocks |
| reading | OpenFanfic, PaginateChapter, ReadPage, SaveProgress, ToggleLike, ToggleBookmark |
| search | IndexFanfic, DeleteFromIndex, Search, Suggest |
| broadcasts | CreateDraft, SetKeyboard, SetSegment, Schedule, Launch, Cancel, EnumerateRecipients, DeliverOne |
| tracking | CreateCode, RecordEvent, QueryFunnel |
| subscriptions | Subscribe, Unsubscribe, NotifySubscribers |
| reports | CreateReport, HandleReport |
| admin | DailySummary, ModeratorLoad, TopFandoms |
