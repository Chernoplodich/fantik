"""Use cases выгрузки id пользователей: общая и по UTM-ссылке."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.tracking.ports import ITrackingRepository
from app.application.users.export_user_ids import (
    ExportAllUserIdsUseCase,
    ExportUserIdsCommand,
    ExportUtmUserIdsCommand,
    ExportUtmUserIdsUseCase,
)
from app.application.users.ports import IUserRepository
from app.core.clock import FrozenClock
from app.core.errors import NotFoundError
from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.tracking.entities import TrackingCode
from app.domain.tracking.value_objects import TrackingCodeStr

from .._fakes import FakeAudit


# ---------- fakes ----------


class FakeUserRepoForExport(IUserRepository):
    """Минимальный fake — реализованы только нужные тестам методы."""

    def __init__(
        self,
        *,
        all_ids: list[int] | None = None,
        by_utm: dict[int, list[int]] | None = None,
    ) -> None:
        self._all_ids = list(all_ids or [])
        self._by_utm = dict(by_utm or {})

    async def list_all_user_ids(self) -> list[UserId]:
        return [UserId(i) for i in self._all_ids]

    async def list_user_ids_by_utm_code(self, code_id: TrackingCodeId) -> list[UserId]:
        return [UserId(i) for i in self._by_utm.get(int(code_id), [])]

    # Остальные методы порта — не используются в этих тестах.
    async def get(self, user_id: UserId) -> Any:  # noqa: ARG002
        raise NotImplementedError

    async def get_by_nick(self, nick_lower: str) -> Any:  # noqa: ARG002
        raise NotImplementedError

    async def save(self, user: Any) -> None:  # noqa: ARG002
        raise NotImplementedError

    async def upsert_touch(self, user: Any) -> None:  # noqa: ARG002
        raise NotImplementedError

    async def get_role(self, user_id: UserId) -> str | None:  # noqa: ARG002
        return None

    async def is_nick_taken(self, nick_lower: str, *, except_user_id: UserId | None = None) -> bool:  # noqa: ARG002
        return False

    async def list_staff(self) -> list[UserId]:
        return []

    async def mark_bot_blocked(self, user_id: UserId) -> None:  # noqa: ARG002
        return None

    async def clear_bot_blocked(self, user_id: UserId) -> None:  # noqa: ARG002
        return None


class FakeTrackingRepoForExport(ITrackingRepository):
    """Тоже минимально — только get_code нужен."""

    def __init__(self, codes: dict[int, TrackingCode]) -> None:
        self._codes = dict(codes)

    async def get_code(self, code_id: TrackingCodeId) -> TrackingCode | None:
        return self._codes.get(int(code_id))

    async def get_code_id(self, code: str) -> Any:  # noqa: ARG002
        raise NotImplementedError

    async def list_codes(self, *, active_only: bool = False) -> Any:  # noqa: ARG002
        raise NotImplementedError

    async def save_code(self, code: TrackingCode) -> Any:  # noqa: ARG002
        raise NotImplementedError

    async def record(self, event: Any) -> None:  # noqa: ARG002
        raise NotImplementedError

    async def has_event_for_user(self, user_id: UserId, event_type: str) -> bool:  # noqa: ARG002
        return False


def _code(code_id: int, code: str) -> TrackingCode:
    return TrackingCode(
        id=TrackingCodeId(code_id),
        code=TrackingCodeStr(code),
        name=f"Demo {code}",
        description=None,
        created_by=UserId(1),
        active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC))


# ---------- ExportAllUserIdsUseCase ----------


class TestExportAllUserIds:
    @pytest.mark.asyncio
    async def test_returns_all_ids_in_order(self, clock: FrozenClock) -> None:
        repo = FakeUserRepoForExport(all_ids=[100, 200, 9000000])
        audit = FakeAudit()
        uc = ExportAllUserIdsUseCase(repo, audit, clock)

        result = await uc(ExportUserIdsCommand(actor_id=42))

        assert result.user_ids == [100, 200, 9000000]
        assert result.label == "all"

    @pytest.mark.asyncio
    async def test_writes_audit_log(self, clock: FrozenClock) -> None:
        repo = FakeUserRepoForExport(all_ids=[1, 2, 3])
        audit = FakeAudit()
        uc = ExportAllUserIdsUseCase(repo, audit, clock)

        await uc(ExportUserIdsCommand(actor_id=42))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry["action"] == "users.export_all"
        assert entry["target_type"] == "users"
        assert entry["payload"] == {"count": 3}
        assert entry["actor_id"] == UserId(42)

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, clock: FrozenClock) -> None:
        repo = FakeUserRepoForExport(all_ids=[])
        uc = ExportAllUserIdsUseCase(repo, FakeAudit(), clock)
        result = await uc(ExportUserIdsCommand(actor_id=1))
        assert result.user_ids == []
        assert result.label == "all"


# ---------- ExportUtmUserIdsUseCase ----------


class TestExportUtmUserIds:
    @pytest.mark.asyncio
    async def test_returns_users_for_code(self, clock: FrozenClock) -> None:
        users = FakeUserRepoForExport(by_utm={7: [101, 202, 303]})
        tracking = FakeTrackingRepoForExport({7: _code(7, "vkpaid001")})
        uc = ExportUtmUserIdsUseCase(users, tracking, FakeAudit(), clock)

        result = await uc(ExportUtmUserIdsCommand(actor_id=42, code_id=7))

        assert result.user_ids == [101, 202, 303]
        assert result.label == "utm_vkpaid001"

    @pytest.mark.asyncio
    async def test_unknown_code_raises_not_found(self, clock: FrozenClock) -> None:
        users = FakeUserRepoForExport()
        tracking = FakeTrackingRepoForExport({})
        uc = ExportUtmUserIdsUseCase(users, tracking, FakeAudit(), clock)

        with pytest.raises(NotFoundError):
            await uc(ExportUtmUserIdsCommand(actor_id=42, code_id=999))

    @pytest.mark.asyncio
    async def test_audit_includes_code_and_count(self, clock: FrozenClock) -> None:
        users = FakeUserRepoForExport(by_utm={5: [10, 20]})
        tracking = FakeTrackingRepoForExport({5: _code(5, "tgblog42")})
        audit = FakeAudit()
        uc = ExportUtmUserIdsUseCase(users, tracking, audit, clock)

        await uc(ExportUtmUserIdsCommand(actor_id=42, code_id=5))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry["action"] == "users.export_utm"
        assert entry["target_type"] == "tracking_code"
        assert entry["target_id"] == 5
        assert entry["payload"] == {"code": "tgblog42", "count": 2}

    @pytest.mark.asyncio
    async def test_no_users_returns_empty_list(self, clock: FrozenClock) -> None:
        users = FakeUserRepoForExport(by_utm={7: []})
        tracking = FakeTrackingRepoForExport({7: _code(7, "organic26")})
        uc = ExportUtmUserIdsUseCase(users, tracking, FakeAudit(), clock)

        result = await uc(ExportUtmUserIdsCommand(actor_id=1, code_id=7))

        assert result.user_ids == []
        assert result.label == "utm_organic26"
