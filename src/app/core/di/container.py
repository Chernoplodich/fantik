"""DI-контейнер dishka: описывает, как собирать сервисы и какие у них жизненные циклы."""

from __future__ import annotations

from collections.abc import AsyncIterator

from aiogram import Bot
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.fanfics.add_chapter import AddChapterUseCase
from app.application.fanfics.cancel_submission import CancelSubmissionUseCase
from app.application.fanfics.create_draft import CreateDraftUseCase
from app.application.fanfics.delete_draft_chapter import DeleteDraftChapterUseCase
from app.application.fanfics.get_fanfic_draft import GetFanficDraftUseCase
from app.application.fanfics.list_my_fanfics import ListMyFanficsUseCase
from app.application.fanfics.ports import (
    IAuthorNotifier,
    IChapterRepository,
    IFanficRepository,
    IFanficVersionRepository,
    IOutboxRepository,
    IReferenceReader,
    ITagRepository,
)
from app.application.reading.list_feed import ListFeedUseCase
from app.application.reading.list_my_shelf import ListMyShelfUseCase
from app.application.reading.mark_completed import MarkCompletedUseCase
from app.application.reading.open_fanfic import OpenFanficUseCase
from app.application.reading.paginate_chapter import PaginateChapterUseCase
from app.application.reading.ports import (
    IBookmarksRepository,
    IChapterPagesRepository,
    IFanficFeedReader,
    ILikesRepository,
    IPageCache,
    IProgressThrottle,
    IReadingProgressRepository,
    IReadsCompletedRepository,
    IRepaginationQueue,
)
from app.application.reading.read_page import ReadPageUseCase
from app.application.reading.save_progress import SaveProgressUseCase
from app.application.reading.toggle_bookmark import ToggleBookmarkUseCase
from app.application.reading.toggle_like import ToggleLikeUseCase
from app.application.fanfics.revise_after_rejection import (
    ReviseAfterRejectionUseCase,
)
from app.application.fanfics.submit_for_review import SubmitForReviewUseCase
from app.application.fanfics.update_chapter import UpdateChapterUseCase
from app.application.fanfics.update_fanfic import UpdateFanficUseCase
from app.application.moderation.approve import ApproveUseCase
from app.application.moderation.list_reasons import ListReasonsUseCase
from app.application.moderation.pick_next import PickNextUseCase
from app.application.moderation.ports import (
    IAuditLog,
    IModerationRepository,
    IModeratorNotifier,
    IReasonRepository,
)
from app.application.moderation.reject import RejectUseCase
from app.application.moderation.release_stale_locks import ReleaseStaleLocksUseCase
from app.application.moderation.unlock import UnlockCaseUseCase
from app.application.tracking.ports import ITrackingRepository
from app.application.tracking.record_event import RecordEventUseCase
from app.application.users.agree_to_rules import AgreeToRulesUseCase
from app.application.users.ports import IUserRepository
from app.application.users.register_user import RegisterUserUseCase
from app.application.users.set_author_nick import SetAuthorNickUseCase
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.infrastructure.db.engine import build_engine, build_sessionmaker
from app.infrastructure.db.repositories.audit_log import AuditLogRepository
from app.infrastructure.db.repositories.bookmarks import BookmarksRepository
from app.infrastructure.db.repositories.chapter_pages import (
    ChapterPagesRepository,
)
from app.infrastructure.db.repositories.chapters import ChapterRepository
from app.infrastructure.db.repositories.fanfic_feed import FanficFeedReader
from app.infrastructure.db.repositories.fanfic_versions import (
    FanficVersionRepository,
)
from app.infrastructure.db.repositories.fanfics import FanficRepository
from app.infrastructure.db.repositories.likes import LikesRepository
from app.infrastructure.db.repositories.moderation import ModerationRepository
from app.infrastructure.db.repositories.moderation_reasons import ReasonRepository
from app.infrastructure.db.repositories.outbox import OutboxRepository
from app.infrastructure.db.repositories.reading_progress import (
    ReadingProgressRepository,
)
from app.infrastructure.db.repositories.reads_completed import (
    ReadsCompletedRepository,
)
from app.infrastructure.db.repositories.reference import ReferenceReader
from app.infrastructure.db.repositories.tags import TagRepository
from app.infrastructure.db.repositories.tracking import TrackingRepository
from app.infrastructure.db.repositories.users import UserRepository
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork, UnitOfWork
from app.infrastructure.redis.page_cache import RedisPageCache
from app.infrastructure.redis.pool import build_redis_cache_pool
from app.infrastructure.redis.progress_throttle import RedisProgressThrottle
from app.infrastructure.redis.role_cache import RoleCache
from app.infrastructure.tasks.repagination_queue import TaskiqRepaginationQueue
from app.infrastructure.telegram.bot_factory import build_bot
from app.infrastructure.telegram.mod_notifier import ModeratorNotifier
from app.infrastructure.telegram.notifier import AuthorNotifier


class SettingsProvider(Provider):
    """Singleton-провайдер конфигурации."""

    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return get_settings()


class ClockProvider(Provider):
    scope = Scope.APP

    @provide
    def clock(self) -> Clock:
        return SystemClock()


class DatabaseProvider(Provider):
    """Engine — singleton на процесс, Session — на request."""

    scope = Scope.APP

    @provide
    async def engine(self, settings: Settings) -> AsyncIterator[AsyncEngine]:
        engine = build_engine(settings)
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide
    async def session_factory(
        self, engine: AsyncEngine
    ) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
        yield build_sessionmaker(engine)

    @provide(scope=Scope.REQUEST)
    async def session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    def uow(self, session: AsyncSession) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session)


class RedisProvider(Provider):
    scope = Scope.APP

    @provide
    async def cache_redis(self, settings: Settings) -> AsyncIterator[Redis]:
        pool = build_redis_cache_pool(settings)
        client: Redis = Redis(connection_pool=pool)
        try:
            yield client
        finally:
            await client.aclose()
            await pool.aclose()

    @provide
    def role_cache(self, redis: Redis) -> RoleCache:
        return RoleCache(redis)

    @provide
    def page_cache(self, redis: Redis) -> IPageCache:
        return RedisPageCache(redis)

    @provide
    def progress_throttle(self, redis: Redis) -> IProgressThrottle:
        return RedisProgressThrottle(redis)


class BotProvider(Provider):
    """Bot — singleton на процесс."""

    scope = Scope.APP

    @provide
    async def bot(self, settings: Settings) -> AsyncIterator[Bot]:
        bot = build_bot(settings)
        try:
            yield bot
        finally:
            await bot.session.close()

    @provide
    def notifier(self, bot: Bot) -> IAuthorNotifier:
        return AuthorNotifier(bot)


class QueuesProvider(Provider):
    """Адаптеры TaskIQ-очередей — app-scope, без сессии БД."""

    scope = Scope.APP

    @provide
    def repagination_queue(self) -> IRepaginationQueue:
        return TaskiqRepaginationQueue()


class RepositoriesProvider(Provider):
    """Репозитории — request-scope, так как нуждаются в AsyncSession."""

    scope = Scope.REQUEST

    @provide
    def user_repo(self, session: AsyncSession) -> IUserRepository:
        return UserRepository(session)

    @provide
    def tracking_repo(self, session: AsyncSession) -> ITrackingRepository:
        return TrackingRepository(session)

    @provide
    def fanfic_repo(self, session: AsyncSession) -> IFanficRepository:
        return FanficRepository(session)

    @provide
    def chapter_repo(self, session: AsyncSession) -> IChapterRepository:
        return ChapterRepository(session)

    @provide
    def tag_repo(self, session: AsyncSession) -> ITagRepository:
        return TagRepository(session)

    @provide
    def version_repo(self, session: AsyncSession) -> IFanficVersionRepository:
        return FanficVersionRepository(session)

    @provide
    def reference_reader(self, session: AsyncSession) -> IReferenceReader:
        return ReferenceReader(session)

    @provide
    def outbox_repo(self, session: AsyncSession) -> IOutboxRepository:
        return OutboxRepository(session)

    @provide
    def moderation_repo(self, session: AsyncSession) -> IModerationRepository:
        return ModerationRepository(session)

    @provide
    def reason_repo(self, session: AsyncSession) -> IReasonRepository:
        return ReasonRepository(session)

    @provide
    def audit_log(self, session: AsyncSession) -> IAuditLog:
        return AuditLogRepository(session)

    @provide
    def mod_notifier(self, bot: Bot, users: IUserRepository) -> IModeratorNotifier:
        return ModeratorNotifier(bot, users)

    # ---------- reading ----------

    @provide
    def chapter_pages_repo(
        self, session: AsyncSession
    ) -> IChapterPagesRepository:
        return ChapterPagesRepository(session)

    @provide
    def bookmarks_repo(self, session: AsyncSession) -> IBookmarksRepository:
        return BookmarksRepository(session)

    @provide
    def likes_repo(self, session: AsyncSession) -> ILikesRepository:
        return LikesRepository(session)

    @provide
    def reads_completed_repo(
        self, session: AsyncSession
    ) -> IReadsCompletedRepository:
        return ReadsCompletedRepository(session)

    @provide
    def reading_progress_repo(
        self, session: AsyncSession
    ) -> IReadingProgressRepository:
        return ReadingProgressRepository(session)

    @provide
    def fanfic_feed_reader(
        self, session: AsyncSession
    ) -> IFanficFeedReader:
        return FanficFeedReader(session)


class UseCasesProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def register_user(
        self,
        uow: UnitOfWork,
        users: IUserRepository,
        tracking: ITrackingRepository,
        clock: Clock,
    ) -> RegisterUserUseCase:
        return RegisterUserUseCase(uow, users, tracking, clock)

    @provide
    def set_author_nick(
        self,
        uow: UnitOfWork,
        users: IUserRepository,
    ) -> SetAuthorNickUseCase:
        return SetAuthorNickUseCase(uow, users)

    @provide
    def agree_to_rules(
        self,
        uow: UnitOfWork,
        users: IUserRepository,
        clock: Clock,
    ) -> AgreeToRulesUseCase:
        return AgreeToRulesUseCase(uow, users, clock)

    @provide
    def record_event(
        self,
        uow: UnitOfWork,
        tracking: ITrackingRepository,
        users: IUserRepository,
        clock: Clock,
    ) -> RecordEventUseCase:
        return RecordEventUseCase(uow, tracking, users, clock)

    # ---------- fanfics ----------

    @provide
    def create_draft(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        tags: ITagRepository,
        reference: IReferenceReader,
        users: IUserRepository,
        clock: Clock,
    ) -> CreateDraftUseCase:
        return CreateDraftUseCase(uow, fanfics, tags, reference, users, clock)

    @provide
    def update_fanfic(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        tags: ITagRepository,
        reference: IReferenceReader,
        clock: Clock,
    ) -> UpdateFanficUseCase:
        return UpdateFanficUseCase(uow, fanfics, tags, reference, clock)

    @provide
    def add_chapter(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        clock: Clock,
        settings: Settings,
    ) -> AddChapterUseCase:
        return AddChapterUseCase(uow, fanfics, chapters, clock, settings)

    @provide
    def update_chapter(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        clock: Clock,
        settings: Settings,
    ) -> UpdateChapterUseCase:
        return UpdateChapterUseCase(uow, fanfics, chapters, clock, settings)

    @provide
    def delete_draft_chapter(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
    ) -> DeleteDraftChapterUseCase:
        return DeleteDraftChapterUseCase(uow, fanfics, chapters)

    @provide
    def submit_for_review(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        versions: IFanficVersionRepository,
        moderation: IModerationRepository,
        outbox: IOutboxRepository,
        users: IUserRepository,
        clock: Clock,
        settings: Settings,
        mod_notifier: IModeratorNotifier,
    ) -> SubmitForReviewUseCase:
        return SubmitForReviewUseCase(
            uow,
            fanfics,
            chapters,
            versions,
            moderation,
            outbox,
            users,
            clock,
            settings,
            mod_notifier,
        )

    @provide
    def cancel_submission(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        moderation: IModerationRepository,
        clock: Clock,
    ) -> CancelSubmissionUseCase:
        return CancelSubmissionUseCase(uow, fanfics, chapters, moderation, clock)

    @provide
    def revise_after_rejection(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        clock: Clock,
    ) -> ReviseAfterRejectionUseCase:
        return ReviseAfterRejectionUseCase(uow, fanfics, clock)

    @provide
    def get_fanfic_draft(
        self,
        fanfics: IFanficRepository,
        tags: ITagRepository,
    ) -> GetFanficDraftUseCase:
        return GetFanficDraftUseCase(fanfics, tags)

    @provide
    def list_my_fanfics(self, fanfics: IFanficRepository) -> ListMyFanficsUseCase:
        return ListMyFanficsUseCase(fanfics)

    # ---------- moderation ----------

    @provide
    def pick_next(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        fanfics: IFanficRepository,
        tags: ITagRepository,
        clock: Clock,
    ) -> PickNextUseCase:
        return PickNextUseCase(uow, moderation, fanfics, tags, clock)

    @provide
    def list_reasons(self, reasons: IReasonRepository) -> ListReasonsUseCase:
        return ListReasonsUseCase(reasons)

    @provide
    def approve_uc(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        versions: IFanficVersionRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        notifier: IAuthorNotifier,
        clock: Clock,
    ) -> ApproveUseCase:
        return ApproveUseCase(
            uow, moderation, fanfics, chapters, versions, outbox, audit, notifier, clock
        )

    @provide
    def reject_uc(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        reasons: IReasonRepository,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        notifier: IAuthorNotifier,
        clock: Clock,
    ) -> RejectUseCase:
        return RejectUseCase(
            uow, moderation, reasons, fanfics, chapters, outbox, audit, notifier, clock
        )

    @provide
    def unlock_uc(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
    ) -> UnlockCaseUseCase:
        return UnlockCaseUseCase(uow, moderation)

    @provide
    def release_stale_locks(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        clock: Clock,
    ) -> ReleaseStaleLocksUseCase:
        return ReleaseStaleLocksUseCase(uow, moderation, clock)

    # ---------- reading ----------

    @provide
    def paginate_chapter_uc(
        self,
        uow: UnitOfWork,
        chapters: IChapterRepository,
        pages: IChapterPagesRepository,
        page_cache: IPageCache,
    ) -> PaginateChapterUseCase:
        return PaginateChapterUseCase(uow, chapters, pages, page_cache)

    @provide
    def open_fanfic_uc(
        self,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        progress: IReadingProgressRepository,
    ) -> OpenFanficUseCase:
        return OpenFanficUseCase(fanfics, chapters, progress)

    @provide
    def read_page_uc(
        self,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        pages: IChapterPagesRepository,
        page_cache: IPageCache,
        bookmarks: IBookmarksRepository,
        likes: ILikesRepository,
        reads_completed: IReadsCompletedRepository,
    ) -> ReadPageUseCase:
        return ReadPageUseCase(
            fanfics, chapters, pages, page_cache, bookmarks, likes, reads_completed
        )

    @provide
    def save_progress_uc(
        self,
        uow: UnitOfWork,
        progress: IReadingProgressRepository,
        throttle: IProgressThrottle,
        clock: Clock,
    ) -> SaveProgressUseCase:
        return SaveProgressUseCase(uow, progress, throttle, clock)

    @provide
    def toggle_like_uc(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        likes: ILikesRepository,
        clock: Clock,
    ) -> ToggleLikeUseCase:
        return ToggleLikeUseCase(uow, fanfics, likes, clock)

    @provide
    def toggle_bookmark_uc(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        bookmarks: IBookmarksRepository,
        clock: Clock,
    ) -> ToggleBookmarkUseCase:
        return ToggleBookmarkUseCase(uow, fanfics, bookmarks, clock)

    @provide
    def mark_completed_uc(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        reads_completed: IReadsCompletedRepository,
        outbox: IOutboxRepository,
        clock: Clock,
    ) -> MarkCompletedUseCase:
        return MarkCompletedUseCase(
            uow, fanfics, chapters, reads_completed, outbox, clock
        )

    @provide
    def list_feed_uc(self, feed: IFanficFeedReader) -> ListFeedUseCase:
        return ListFeedUseCase(feed)

    @provide
    def list_my_shelf_uc(
        self,
        fanfics: IFanficRepository,
        bookmarks: IBookmarksRepository,
        likes: ILikesRepository,
        progress: IReadingProgressRepository,
    ) -> ListMyShelfUseCase:
        return ListMyShelfUseCase(fanfics, bookmarks, likes, progress)


def build_container() -> AsyncContainer:
    """Собрать контейнер со всеми провайдерами. Вызывать один раз на процесс."""
    # AiogramProvider импортируем лениво, чтобы контейнер не требовал aiogram,
    # когда используется в воркере (воркер не всегда нуждается в нём).
    from dishka.integrations.aiogram import AiogramProvider

    return make_async_container(
        SettingsProvider(),
        ClockProvider(),
        DatabaseProvider(),
        RedisProvider(),
        BotProvider(),
        QueuesProvider(),
        RepositoriesProvider(),
        UseCasesProvider(),
        AiogramProvider(),
    )
