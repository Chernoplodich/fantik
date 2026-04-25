"""Порты для домена пользователей."""

from __future__ import annotations

from typing import Protocol

from app.domain.shared.types import TrackingCodeId, UserId
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

    async def is_nick_taken(
        self, nick_lower: str, *, except_user_id: UserId | None = None
    ) -> bool: ...

    async def list_staff(self) -> list[UserId]:
        """Вернуть id всех пользователей с ролью moderator/admin (для нотификаций)."""
        ...

    async def mark_bot_blocked(self, user_id: UserId) -> None:
        """Отметить, что пользователь заблокировал бота (идемпотентно)."""
        ...

    async def clear_bot_blocked(self, user_id: UserId) -> None:
        """Снять отметку блока (юзер нажал /start / явно нам написал)."""
        ...

    async def list_all_user_ids(self) -> list[UserId]:
        """Все id пользователей (отсортированные по id asc).

        Включая banned / blocked_bot — это раздел админ-выгрузки, фильтрация
        делается на стороне вызывающего (use case), если нужна.
        """
        ...

    async def list_user_ids_by_utm_code(self, code_id: TrackingCodeId) -> list[UserId]:
        """Все id пользователей, у которых first-touch UTM = указанному коду.

        Сравнивается `users.utm_source_code_id`. Сортировка по id asc.
        """
        ...
