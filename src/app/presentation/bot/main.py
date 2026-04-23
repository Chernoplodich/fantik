"""Точка входа bot-процесса: сборка Dispatcher, middleware, routers, запуск polling/webhook."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import RunMode, Settings
from app.core.di import build_container
from app.core.logging import get_logger, setup_logging
from app.infrastructure.redis.pool import build_redis_fsm_pool
from app.presentation.bot.health import build_health_app
from app.presentation.bot.middlewares.ban_check import BanCheckMiddleware
from app.presentation.bot.middlewares.logging import LoggingMiddleware
from app.presentation.bot.middlewares.role import RoleMiddleware
from app.presentation.bot.middlewares.throttle import ThrottleMiddleware
from app.presentation.bot.middlewares.user_upsert import UserUpsertMiddleware
from app.presentation.bot.routers import author_create as author_create_router
from app.presentation.bot.routers import author_manage as author_manage_router
from app.presentation.bot.routers import browse as browse_router
from app.presentation.bot.routers import errors as errors_router
from app.presentation.bot.routers import inline_search as inline_search_router
from app.presentation.bot.routers import menu as menu_router
from app.presentation.bot.routers import moderation as moderation_router
from app.presentation.bot.routers import onboarding as onboarding_router
from app.presentation.bot.routers import profile as profile_router
from app.presentation.bot.routers import reader as reader_router
from app.presentation.bot.routers import shelf as shelf_router
from app.presentation.bot.routers import start as start_router

log = get_logger(__name__)


def _build_dispatcher(settings: Settings, fsm_pool: ConnectionPool) -> Dispatcher:
    storage = RedisStorage(
        Redis(connection_pool=fsm_pool),
        state_ttl=3600,
        data_ttl=3600,
    )
    dp = Dispatcher(storage=storage)

    # Middleware регистрируются позже (после setup_dishka), чтобы они стояли
    # ПОСЛЕ ContainerMiddleware — иначе data[CONTAINER_NAME] отсутствует.
    dp.include_router(errors_router.router)
    dp.include_router(start_router.router)
    dp.include_router(onboarding_router.router)
    dp.include_router(profile_router.router)
    dp.include_router(author_create_router.router)
    dp.include_router(author_manage_router.router)
    dp.include_router(moderation_router.router)
    dp.include_router(browse_router.router)
    dp.include_router(reader_router.router)
    dp.include_router(shelf_router.router)
    dp.include_router(inline_search_router.router)
    dp.include_router(menu_router.router)
    return dp


def _register_middlewares(dp: Dispatcher) -> None:
    """Порядок важен: logging → user_upsert → ban_check → throttle → role.

    Регистрируется ПОСЛЕ setup_dishka, чтобы ContainerMiddleware отработал
    раньше и положил dishka-контейнер в `data`.
    """
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(UserUpsertMiddleware())
    dp.update.outer_middleware(BanCheckMiddleware())
    dp.update.outer_middleware(ThrottleMiddleware())
    dp.update.outer_middleware(RoleMiddleware())


async def _seed_admins(container: AsyncContainer, settings: Settings) -> None:
    """Засеять роль admin для пользователей из ADMIN_TG_IDS (создаст запись-заглушку,
    если /start ещё не выполнялся)."""
    if not settings.admin_tg_ids:
        return
    from app.application.users.ports import IUserRepository
    from app.domain.shared.types import UserId
    from app.domain.users.entities import User as UserEntity
    from app.domain.users.value_objects import Role
    from app.infrastructure.db.unit_of_work import UnitOfWork

    async with container() as req:
        users: IUserRepository = await req.get(IUserRepository)
        uow: UnitOfWork = await req.get(UnitOfWork)
        async with uow:
            for tg_id in settings.admin_tg_ids:
                u = await users.get(UserId(tg_id))
                if u is None:
                    u = UserEntity(id=UserId(tg_id), role=Role.ADMIN)
                    await users.save(u)
                elif u.role != Role.ADMIN:
                    u.role = Role.ADMIN
                    await users.save(u)
            await uow.commit()
    log.info("admins_seeded", count=len(settings.admin_tg_ids))


async def _run_polling(bot: Bot, dp: Dispatcher, health_runner: web.AppRunner) -> None:
    log.info("bot_starting_polling")
    try:
        await dp.start_polling(bot, handle_signals=True)
    finally:
        await health_runner.cleanup()


async def _run_webhook(
    bot: Bot, dp: Dispatcher, settings: Settings, health_app: web.Application
) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    if not settings.webhook_full_url:
        raise RuntimeError("BOT_RUN_MODE=webhook, но WEBHOOK_BASE_URL не задан.")
    await bot.set_webhook(
        url=settings.webhook_full_url,
        secret_token=settings.webhook_secret.get_secret_value() or None,
        drop_pending_updates=True,
    )
    log.info("webhook_set", url=settings.webhook_full_url)

    handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret.get_secret_value() or None,
    )
    from urllib.parse import urlparse

    path = urlparse(settings.webhook_full_url).path
    handler.register(health_app, path=path)
    setup_application(health_app, dp, bot=bot)

    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.webhook_host, port=settings.webhook_port)
    await site.start()
    log.info("webhook_listening", host=settings.webhook_host, port=settings.webhook_port)
    try:
        # Блокируемся навсегда до SIGTERM
        stop = asyncio.Event()
        await stop.wait()
    finally:
        await runner.cleanup()


async def _bootstrap_search(container: AsyncContainer) -> None:
    """Идемпотентное применение настроек Meilisearch-индекса при старте.

    Best-effort: если Meili недоступен, логируем warning и продолжаем
    (fallback PG FTS всё равно подхватит поиск).
    """
    from meilisearch_python_sdk import AsyncClient as _MeiliClient

    from app.infrastructure.search import settings_bootstrap as _sb

    try:
        client: _MeiliClient = await container.get(_MeiliClient)
        await _sb.apply(client)
        log.info("meili_bootstrap_done")
    except Exception as e:  # noqa: BLE001
        log.warning("meili_bootstrap_failed", error=str(e))


async def main() -> None:
    container = build_container()
    settings = await container.get(Settings)
    setup_logging(settings)
    log.info("bot_init", env=settings.app_env.value)

    # Seed админы до старта хэндлеров
    await _seed_admins(container, settings)

    # Meilisearch settings: идемпотентно применяются один раз при старте.
    await _bootstrap_search(container)

    bot: Bot = await container.get(Bot)

    # FSM storage на Redis FSM DB
    fsm_pool = build_redis_fsm_pool(settings)
    dp = _build_dispatcher(settings, fsm_pool)

    # Регистрация DI в aiogram — после этого FromDishka[T] работает в хэндлерах.
    # setup_dishka добавляет ContainerMiddleware как outer — ДО наших outer middlewares.
    setup_dishka(container=container, router=dp, auto_inject=True)
    _register_middlewares(dp)

    # /healthz + /metrics
    engine: AsyncEngine = await container.get(AsyncEngine)
    cache_redis: Redis = await container.get(Redis)
    health_app = build_health_app(engine, cache_redis, settings)
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.health_host, port=settings.health_port)

    try:
        if settings.bot_run_mode == RunMode.POLLING:
            await site.start()
            log.info("health_listening", host=settings.health_host, port=settings.health_port)
            await _run_polling(bot, dp, runner)
        else:
            await _run_webhook(bot, dp, settings, health_app)
    finally:
        # bot.session закроется при container.close() (BotProvider async gen finally)
        await container.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("bot_stopped")
