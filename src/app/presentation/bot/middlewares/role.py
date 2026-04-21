"""Role middleware: подгружает роль из Redis-кэша, при miss — из БД.

Кладёт в data ключ 'role' (string: 'user'|'moderator'|'admin'), используется фильтрами.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from dishka import AsyncContainer
from dishka.integrations.aiogram import CONTAINER_NAME

from app.application.users.ports import IUserRepository
from app.domain.shared.types import UserId
from app.domain.users.value_objects import Role
from app.infrastructure.redis.role_cache import RoleCache


class RoleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is None or from_user.is_bot:
            data["role"] = Role.USER
            return await handler(event, data)

        container: AsyncContainer | None = data.get(CONTAINER_NAME)
        role_str: str | None = None
        if container is not None:
            async with container() as req:
                cache: RoleCache = await req.get(RoleCache)
                cached = await cache.get(from_user.id)
                if cached is not None:
                    role_str = cached
                else:
                    users: IUserRepository = await req.get(IUserRepository)
                    role_str = await users.get_role(UserId(from_user.id))
                    if role_str is not None:
                        await cache.set(from_user.id, role_str)
        data["role"] = Role(role_str) if role_str else Role.USER
        return await handler(event, data)
