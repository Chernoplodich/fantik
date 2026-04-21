"""Фильтры по ролям. Используют `role`, положенное RoleMiddleware в data."""

from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import TelegramObject

from app.domain.users.value_objects import Role


class IsAdmin(Filter):
    async def __call__(self, _: TelegramObject, role: Role = Role.USER) -> bool:
        return role == Role.ADMIN


class IsModerator(Filter):
    async def __call__(self, _: TelegramObject, role: Role = Role.USER) -> bool:
        return role in (Role.MODERATOR, Role.ADMIN)
