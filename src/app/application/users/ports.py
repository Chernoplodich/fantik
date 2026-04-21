"""Порты для домена пользователей."""

from __future__ import annotations

from typing import Protocol

from app.domain.shared.types import UserId
from app.domain.users.entities import User


class IUserRepository(Protocol):
    async def get(self, user_id: UserId) -> User | None: ...

    async def get_by_nick(self, nick_lower: str) -> User | None: ...

    async def save(self, user: User) -> None: ...

    async def upsert_touch(self, user: User) -> None:
        """Атомарно upsert'ить пользователя (ON CONFLICT DO UPDATE last_seen/username/...)."""
        ...

    async def get_role(self, user_id: UserId) -> str | None:
        """Быстрый запрос только роли — для RoleMiddleware."""
        ...

    async def is_nick_taken(self, nick_lower: str, *, except_user_id: UserId | None = None) -> bool:
        ...
