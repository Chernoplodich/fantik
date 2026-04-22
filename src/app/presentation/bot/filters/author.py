"""Фильтры авторства: HasAuthorNick."""

from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import TelegramObject
from dishka.integrations.aiogram import FromDishka

from app.application.users.ports import IUserRepository
from app.domain.shared.types import UserId


class HasAuthorNick(Filter):
    """Пропускает только пользователей с уже заданным author_nick."""

    async def __call__(
        self,
        event: TelegramObject,
        users: FromDishka[IUserRepository],
    ) -> bool:
        user_id = getattr(event, "from_user", None)
        if user_id is None:
            return False
        u = await users.get(UserId(user_id.id))
        return u is not None and u.author_nick is not None
