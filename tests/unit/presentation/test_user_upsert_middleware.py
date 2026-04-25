"""UserUpsertMiddleware: создание user'а — задача роутера /start, не middleware.

Регрессия: раньше middleware при первом апдейте СОЗДАВАЛ запись в users
(минимальную, без UTM/agreed_at). Это «съедало» нового юзера, и когда
следом отрабатывал /start handler, RegisterUserUseCase видел `existing
is not None` → `is_new=False` → tracking-event'ы и UTM-атрибуция терялись.

После фикса middleware только TOUCH'ит существующих и пропускает
несуществующих — handler /start сам зарегистрирует с правильным UTM.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, Self

import pytest

from app.application.users.ports import IUserRepository
from app.domain.shared.types import UserId
from app.domain.users.entities import User
from app.presentation.bot.middlewares.user_upsert import UserUpsertMiddleware


@dataclass
class FakeUow:
    committed: bool = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: object, exc: object, tb: TracebackType | None
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None

    def record_events(self, events: list[Any]) -> None:
        return None

    def collect_events(self) -> list[Any]:
        return []


class FakeUsers(IUserRepository):
    def __init__(self) -> None:
        self._by_id: dict[UserId, User] = {}
        self.save_calls = 0

    async def get(self, user_id: UserId) -> User | None:
        return self._by_id.get(user_id)

    async def save(self, user: User) -> None:
        self._by_id[user.id] = user
        self.save_calls += 1

    # Остальные методы порта — не используются.
    async def get_by_nick(self, nick_lower: str) -> User | None:  # noqa: ARG002
        return None

    async def upsert_touch(self, user: User) -> None:
        await self.save(user)

    async def get_role(self, user_id: UserId) -> str | None:  # noqa: ARG002
        return None

    async def is_nick_taken(
        self, nick_lower: str, *, except_user_id: UserId | None = None
    ) -> bool:  # noqa: ARG002
        return False

    async def list_staff(self) -> list[UserId]:
        return []

    async def mark_bot_blocked(self, user_id: UserId) -> None:  # noqa: ARG002
        return None

    async def clear_bot_blocked(self, user_id: UserId) -> None:  # noqa: ARG002
        return None

    async def list_all_user_ids(self) -> list[UserId]:
        return []

    async def list_user_ids_by_utm_code(self, code_id: Any) -> list[UserId]:  # noqa: ARG002
        return []


class FakeContainer:
    """Эмулирует dishka AsyncContainer.__call__() как async-context manager."""

    def __init__(self, registry: dict[type, object]) -> None:
        self._registry = registry

    def __call__(self) -> "FakeContainer":  # noqa: D401
        return self

    async def __aenter__(self) -> "FakeContainer":
        return self

    async def __aexit__(
        self, exc_type: object, exc: object, tb: TracebackType | None
    ) -> None:
        return None

    async def get(self, t: type) -> object:
        for k, v in self._registry.items():
            if isinstance(v, k):
                if t is k or issubclass(k, t):
                    return v
        # fallback по имени (Protocol-types)
        return next(iter(self._registry.values()))


@dataclass
class FakeFromUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_bot: bool = False


@dataclass
class FakeEvent:
    from_user: FakeFromUser | None = None


@dataclass
class HandlerCalls:
    count: int = 0
    last_data: dict[str, Any] = field(default_factory=dict)


def _make_handler() -> tuple[Callable[..., Awaitable[Any]], HandlerCalls]:
    calls = HandlerCalls()

    async def handler(event: Any, data: dict[str, Any]) -> str:  # noqa: ARG001
        calls.count += 1
        calls.last_data = dict(data)
        return "ok"

    return handler, calls


def _ctx(users: IUserRepository, uow: FakeUow) -> dict[str, Any]:
    container = FakeContainer({IUserRepository: users, type(uow): uow})

    async def _aget(t: type) -> object:
        if t is IUserRepository:
            return users
        return uow

    container.get = _aget  # type: ignore[method-assign]
    from dishka.integrations.aiogram import CONTAINER_NAME

    return {CONTAINER_NAME: container}


class TestUserUpsertMiddleware:
    @pytest.mark.asyncio
    async def test_does_not_create_unknown_user(self) -> None:
        """Регрессия: middleware НЕ должен создавать user'а в БД.

        Иначе /start handler видит `existing != None` и UTM теряется.
        """
        users, uow = FakeUsers(), FakeUow()
        mw = UserUpsertMiddleware()
        handler, calls = _make_handler()

        event = FakeEvent(from_user=FakeFromUser(id=12345, username="bob"))
        result = await mw(handler, event, _ctx(users, uow))

        assert result == "ok"
        assert calls.count == 1
        # Главное: user не создан, save не вызывался.
        assert users.save_calls == 0
        assert await users.get(UserId(12345)) is None

    @pytest.mark.asyncio
    async def test_touches_existing_user_when_stale(self) -> None:
        """Существующий юзер с устаревшим last_seen — должен обновиться."""
        users, uow = FakeUsers(), FakeUow()
        old = datetime.now(UTC) - timedelta(minutes=5)
        await users.save(
            User.register(
                tg_id=12345,
                username="bob",
                first_name="Bob",
                last_name=None,
                language_code="ru",
                utm_code_id=None,
                now=old,
            )
        )
        users.save_calls = 0  # обнулим счётчик после setup

        mw = UserUpsertMiddleware()
        handler, _ = _make_handler()
        event = FakeEvent(from_user=FakeFromUser(id=12345, username="bob_new"))

        await mw(handler, event, _ctx(users, uow))

        assert users.save_calls == 1
        u = await users.get(UserId(12345))
        assert u is not None
        assert u.username == "bob_new"

    @pytest.mark.asyncio
    async def test_skips_bots(self) -> None:
        users, uow = FakeUsers(), FakeUow()
        mw = UserUpsertMiddleware()
        handler, calls = _make_handler()
        event = FakeEvent(from_user=FakeFromUser(id=999, is_bot=True))
        await mw(handler, event, _ctx(users, uow))
        assert calls.count == 1
        assert users.save_calls == 0
