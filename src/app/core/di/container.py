"""DI-контейнер dishka: описывает, как собирать сервисы и какие у них жизненные циклы."""

from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.tracking.ports import ITrackingRepository
from app.application.tracking.record_event import RecordEventUseCase
from app.application.users.agree_to_rules import AgreeToRulesUseCase
from app.application.users.ports import IUserRepository
from app.application.users.register_user import RegisterUserUseCase
from app.application.users.set_author_nick import SetAuthorNickUseCase
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.infrastructure.db.engine import build_engine, build_sessionmaker
from app.infrastructure.db.repositories.tracking import TrackingRepository
from app.infrastructure.db.repositories.users import UserRepository
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork, UnitOfWork
from app.infrastructure.redis.pool import build_redis_cache_pool
from app.infrastructure.redis.role_cache import RoleCache


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


class RepositoriesProvider(Provider):
    """Репозитории — request-scope, так как нуждаются в AsyncSession."""

    scope = Scope.REQUEST

    @provide
    def user_repo(self, session: AsyncSession) -> IUserRepository:
        return UserRepository(session)

    @provide
    def tracking_repo(self, session: AsyncSession) -> ITrackingRepository:
        return TrackingRepository(session)


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
        RepositoriesProvider(),
        UseCasesProvider(),
        AiogramProvider(),
    )
