"""Unit-тест RegisterUserUseCase с in-memory репозиториями и UoW."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

import pytest

from app.application.tracking.ports import ITrackingRepository
from app.application.users.ports import IUserRepository
from app.application.users.register_user import (
    RegisterUserCommand,
    RegisterUserUseCase,
)
from app.core.clock import FrozenClock
from app.domain.shared.events import DomainEvent
from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.tracking.entities import TrackingCode, TrackingEvent
from app.domain.tracking.value_objects import TrackingCodeStr
from app.domain.users.entities import User
from app.domain.users.events import UserRegistered

# ---------- фейковые зависимости ----------


@dataclass
class FakeUow:
    events: list[DomainEvent] = field(default_factory=list)
    committed: bool = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: TracebackType | None) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None: ...

    def record_events(self, events: list[DomainEvent]) -> None:
        self.events.extend(events)

    def collect_events(self) -> list[DomainEvent]:
        return list(self.events)


class FakeUsers(IUserRepository):
    def __init__(self) -> None:
        self._by_id: dict[UserId, User] = {}

    async def get(self, user_id: UserId) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_nick(self, nick_lower: str) -> User | None:
        for u in self._by_id.values():
            if u.author_nick and u.author_nick.lowered == nick_lower:
                return u
        return None

    async def save(self, user: User) -> None:
        self._by_id[user.id] = user

    async def upsert_touch(self, user: User) -> None:
        await self.save(user)

    async def get_role(self, user_id: UserId) -> str | None:
        u = self._by_id.get(user_id)
        return u.role.value if u else None

    async def is_nick_taken(self, nick_lower: str, *, except_user_id: UserId | None = None) -> bool:
        for u in self._by_id.values():
            if u.author_nick and u.author_nick.lowered == nick_lower and u.id != except_user_id:
                return True
        return False


class FakeTracking(ITrackingRepository):
    def __init__(self) -> None:
        self._codes: dict[str, TrackingCode] = {}
        self._events: list[TrackingEvent] = []

    def add_code(self, code: str, cid: int = 1) -> None:
        self._codes[code] = TrackingCode(
            id=TrackingCodeId(cid),
            code=TrackingCodeStr(code),
            name="test",
            description=None,
            created_by=UserId(0),
            active=True,
            created_at=datetime.now(tz=UTC),
        )

    async def get_code_id(self, code: str) -> TrackingCodeId | None:
        c = self._codes.get(code)
        return c.id if c else None

    async def get_code(self, code_id: TrackingCodeId) -> TrackingCode | None:
        for c in self._codes.values():
            if c.id == code_id:
                return c
        return None

    async def list_codes(self, *, active_only: bool = False) -> list[TrackingCode]:
        return [c for c in self._codes.values() if not active_only or c.active]

    async def save_code(self, code: TrackingCode) -> TrackingCode:
        self._codes[str(code.code)] = code
        return code

    async def record(self, event: TrackingEvent) -> None:
        self._events.append(event)

    async def has_event_for_user(self, user_id: UserId, event_type: str) -> bool:
        return any(e.user_id == user_id and e.event_type.value == event_type for e in self._events)

    @property
    def events(self) -> list[TrackingEvent]:
        return list(self._events)


# ---------- тесты ----------


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC))


class TestRegisterUser:
    async def test_new_user_without_utm(self, clock: FrozenClock) -> None:
        users, tracking, uow = FakeUsers(), FakeTracking(), FakeUow()
        uc = RegisterUserUseCase(uow, users, tracking, clock)

        result = await uc(
            RegisterUserCommand(
                tg_id=777,
                username="alice",
                first_name="Alice",
                last_name=None,
                language_code="ru",
                utm_code=None,
            )
        )

        assert result.is_new is True
        assert result.user.id == UserId(777)
        assert result.user.utm_source_code_id is None
        # 'start' + 'register' для новых
        types = [e.event_type.value for e in tracking.events]
        assert types == ["start", "register"]
        # UserRegistered event записан в UoW
        assert any(isinstance(e, UserRegistered) for e in uow.events)
        assert uow.committed

    async def test_existing_user_no_register_event(self, clock: FrozenClock) -> None:
        users, tracking, uow = FakeUsers(), FakeTracking(), FakeUow()
        await users.save(
            User.register(
                tg_id=777,
                username="alice",
                first_name="Alice",
                last_name=None,
                language_code="ru",
                utm_code_id=None,
                now=clock.now(),
            )
        )
        uc = RegisterUserUseCase(uow, users, tracking, clock)
        result = await uc(
            RegisterUserCommand(
                tg_id=777,
                username="alice",
                first_name="Alice",
                last_name=None,
                language_code="ru",
                utm_code=None,
            )
        )

        assert result.is_new is False
        # Повторный /start существующего юзера не пишет tracking-событий
        # (иначе UTM-ссылка раздувается за счёт уже зарегистрированных).
        types = [e.event_type.value for e in tracking.events]
        assert types == []

    async def test_new_user_with_valid_utm(self, clock: FrozenClock) -> None:
        users, tracking, uow = FakeUsers(), FakeTracking(), FakeUow()
        tracking.add_code("x7kqA9pT", cid=42)
        uc = RegisterUserUseCase(uow, users, tracking, clock)

        result = await uc(
            RegisterUserCommand(
                tg_id=500,
                username=None,
                first_name="B",
                last_name=None,
                language_code=None,
                utm_code="x7kqA9pT",
            )
        )

        assert result.is_new is True
        assert result.user.utm_source_code_id == TrackingCodeId(42)
        assert all(e.code_id == TrackingCodeId(42) for e in tracking.events)

    async def test_invalid_utm_is_silently_dropped(self, clock: FrozenClock) -> None:
        users, tracking, uow = FakeUsers(), FakeTracking(), FakeUow()
        uc = RegisterUserUseCase(uow, users, tracking, clock)
        result = await uc(
            RegisterUserCommand(
                tg_id=42,
                username=None,
                first_name=None,
                last_name=None,
                language_code=None,
                utm_code="bad code!",
            )
        )
        assert result.is_new is True
        assert result.user.utm_source_code_id is None
