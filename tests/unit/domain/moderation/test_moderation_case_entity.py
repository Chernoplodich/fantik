"""Unit-тесты ModerationCase."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.fanfics.value_objects import MqDecision, MqKind
from app.domain.moderation.entities import ModerationCase
from app.domain.moderation.exceptions import (
    CannotModerateOwnWorkError,
    CaseAlreadyDecidedError,
    CaseNotLockedByThisModeratorError,
    ReasonsRequiredForRejectError,
)
from app.domain.shared.types import (
    FanficId,
    ModerationCaseId,
    UserId,
)

NOW = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)


def _make_case(submitted_by: int = 1) -> ModerationCase:
    return ModerationCase(
        id=ModerationCaseId(10),
        fic_id=FanficId(1),
        chapter_id=None,
        kind=MqKind.FIC_FIRST_PUBLISH,
        submitted_by=UserId(submitted_by),
        submitted_at=NOW,
    )


class TestModerationCase:
    def test_lock_and_unlock(self) -> None:
        case = _make_case(submitted_by=1)
        case.lock(moderator_id=UserId(2), now=NOW)
        assert case.locked_by == UserId(2)
        assert case.is_locked(now=NOW)
        case.unlock(moderator_id=UserId(2), now=NOW)
        assert case.locked_by is None

    def test_cannot_lock_own_work(self) -> None:
        case = _make_case(submitted_by=2)
        with pytest.raises(CannotModerateOwnWorkError):
            case.lock(moderator_id=UserId(2), now=NOW)

    def test_approve_requires_active_lock(self) -> None:
        case = _make_case()
        with pytest.raises(CaseNotLockedByThisModeratorError):
            case.approve(moderator_id=UserId(2), comment=None, entities=[], now=NOW)

    def test_approve_happy_path(self) -> None:
        case = _make_case()
        case.lock(moderator_id=UserId(2), now=NOW)
        case.approve(moderator_id=UserId(2), comment="ok", entities=[], now=NOW)
        assert case.decision == MqDecision.APPROVED
        assert case.decided_by == UserId(2)

    def test_second_decision_rejected(self) -> None:
        case = _make_case()
        case.lock(moderator_id=UserId(2), now=NOW)
        case.approve(moderator_id=UserId(2), comment=None, entities=[], now=NOW)
        with pytest.raises(CaseAlreadyDecidedError):
            case.reject(
                moderator_id=UserId(2),
                reason_ids=[1],
                comment=None,
                entities=[],
                now=NOW,
            )

    def test_reject_requires_reasons(self) -> None:
        case = _make_case()
        case.lock(moderator_id=UserId(2), now=NOW)
        with pytest.raises(ReasonsRequiredForRejectError):
            case.reject(
                moderator_id=UserId(2),
                reason_ids=[],
                comment=None,
                entities=[],
                now=NOW,
            )

    def test_lock_expired_approve_fails(self) -> None:
        case = _make_case()
        case.lock(moderator_id=UserId(2), now=NOW)
        later = NOW + timedelta(minutes=30)
        with pytest.raises(CaseNotLockedByThisModeratorError):
            case.approve(moderator_id=UserId(2), comment=None, entities=[], now=later)
