"""Unit-тест ReleaseStaleLocksUseCase."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.application.moderation.release_stale_locks import (
    ReleaseStaleLocksUseCase,
)
from app.core.clock import FrozenClock
from app.domain.fanfics.value_objects import MqKind
from app.domain.moderation.entities import ModerationCase
from app.domain.shared.types import FanficId, ModerationCaseId, UserId

from ._fakes import FakeModeration, FakeUow


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 21, 13, 0, 0, tzinfo=UTC))


class TestReleaseStaleLocks:
    async def test_releases_expired(self, clock: FrozenClock) -> None:
        moderation = FakeModeration()
        case = ModerationCase(
            id=ModerationCaseId(1),
            fic_id=FanficId(1),
            chapter_id=None,
            kind=MqKind.FIC_FIRST_PUBLISH,
            submitted_by=UserId(1),
            submitted_at=clock.now() - timedelta(hours=1),
            locked_by=UserId(99),
            locked_until=clock.now() - timedelta(minutes=10),
        )
        moderation._by_id[case.id] = case  # noqa: SLF001

        uc = ReleaseStaleLocksUseCase(FakeUow(), moderation, clock)
        released = await uc()
        assert released == 1
        assert case.locked_by is None
        assert case.locked_until is None
