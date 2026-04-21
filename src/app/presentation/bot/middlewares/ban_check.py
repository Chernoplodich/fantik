"""Ban check: если пользователь забанен — ответить и отменить дальнейшую обработку."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from dishka import AsyncContainer
from dishka.integrations.aiogram import CONTAINER_NAME

from app.application.users.ports import IUserRepository
from app.domain.shared.types import UserId
from app.presentation.bot.texts.ru import t


class BanCheckMiddleware(BaseMiddleware):
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
        if container is None:
            return await handler(event, data)

        async with container() as req:
            users: IUserRepository = await req.get(IUserRepository)
            user = await users.get(UserId(from_user.id))

        if user is None or not user.is_banned:
            return await handler(event, data)

        # Пользователь забанен — отвечаем и прерываем цепочку
        msg = t("banned", reason=user.banned_reason or "не указана")
        if isinstance(event, CallbackQuery):
            await event.answer(msg, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(msg)
        return None
