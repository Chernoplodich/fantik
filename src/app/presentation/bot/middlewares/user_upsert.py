"""Middleware: upsert пользователя при каждом апдейте. ТОЛЬКО last_seen / имя / username.

Регистрация полноценная (включая запись tracking-события) выполняется в /start hand'е.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from dishka import AsyncContainer
from dishka.integrations.aiogram import CONTAINER_NAME

from app.application.users.ports import IUserRepository
from app.domain.shared.types import UserId
from app.domain.users.entities import User as UserEntity
from app.infrastructure.db.unit_of_work import UnitOfWork

_UPDATE_EVERY_SECONDS = 60  # если last_seen моложе — не дергаем DB


class UserUpsertMiddleware(BaseMiddleware):
    """Берёт контейнер из data (его положил dishka middleware) и делает upsert."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is None or from_user.is_bot:
            return await handler(event, data)

        container: AsyncContainer | None = data.get(CONTAINER_NAME)
        if container is not None:
            async with container() as req:
                users: IUserRepository = await req.get(IUserRepository)
                uow: UnitOfWork = await req.get(UnitOfWork)
                now = datetime.now(tz=UTC)
                async with uow:
                    existing = await users.get(UserId(from_user.id))
                    if existing is None:
                        # Создадим минимального пользователя; /start сделает полную регистрацию.
                        user = UserEntity(
                            id=UserId(from_user.id),
                            username=from_user.username,
                            first_name=from_user.first_name,
                            last_name=from_user.last_name,
                            language_code=from_user.language_code,
                            created_at=now,
                            last_seen_at=now,
                        )
                        await users.save(user)
                        await uow.commit()
                    elif (
                        existing.last_seen_at is None
                        or (now - existing.last_seen_at).total_seconds() >= _UPDATE_EVERY_SECONDS
                        or existing.username != from_user.username
                    ):
                        existing.touch(
                            now=now,
                            username=from_user.username,
                            first_name=from_user.first_name,
                            last_name=from_user.last_name,
                            language_code=from_user.language_code,
                        )
                        await users.save(existing)
                        await uow.commit()
        return await handler(event, data)
