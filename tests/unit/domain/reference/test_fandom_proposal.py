"""State machine FandomProposal: pending → approved | rejected."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.errors import ConflictError
from app.domain.reference.entities import FandomProposal
from app.domain.reference.events import (
    FandomProposalApproved,
    FandomProposalRejected,
)
from app.domain.reference.value_objects import FandomProposalStatus, ProposalId
from app.domain.shared.types import FandomId, UserId


def _new(status: FandomProposalStatus = FandomProposalStatus.PENDING) -> FandomProposal:
    return FandomProposal(
        id=ProposalId(1),
        requested_by=UserId(42),
        name="Тестовый фандом",
        category_hint="anime",
        status=status,
    )


class TestApprove:
    def test_pending_can_be_approved(self) -> None:
        p = _new()
        now = datetime.now(tz=UTC)
        p.approve(
            moderator_id=UserId(7),
            fandom_id=FandomId(99),
            comment="ok",
            now=now,
        )
        assert p.status is FandomProposalStatus.APPROVED
        assert p.reviewed_by == UserId(7)
        assert p.reviewed_at == now
        assert p.created_fandom_id == FandomId(99)
        events = p.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], FandomProposalApproved)
        assert events[0].fandom_id == FandomId(99)

    def test_already_approved_cant_be_approved_again(self) -> None:
        p = _new(status=FandomProposalStatus.APPROVED)
        with pytest.raises(ConflictError):
            p.approve(
                moderator_id=UserId(7),
                fandom_id=FandomId(99),
                comment=None,
                now=datetime.now(tz=UTC),
            )

    def test_already_rejected_cant_be_approved(self) -> None:
        p = _new(status=FandomProposalStatus.REJECTED)
        with pytest.raises(ConflictError):
            p.approve(
                moderator_id=UserId(7),
                fandom_id=FandomId(99),
                comment=None,
                now=datetime.now(tz=UTC),
            )


class TestReject:
    def test_pending_can_be_rejected_with_reason(self) -> None:
        p = _new()
        now = datetime.now(tz=UTC)
        p.reject(moderator_id=UserId(7), reason="дубль", now=now)
        assert p.status is FandomProposalStatus.REJECTED
        assert p.decision_comment == "дубль"
        events = p.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], FandomProposalRejected)
        assert events[0].reason == "дубль"

    def test_already_rejected_cant_be_rejected_again(self) -> None:
        p = _new(status=FandomProposalStatus.REJECTED)
        with pytest.raises(ConflictError):
            p.reject(
                moderator_id=UserId(7),
                reason=None,
                now=datetime.now(tz=UTC),
            )

    def test_reject_without_reason(self) -> None:
        p = _new()
        p.reject(
            moderator_id=UserId(7),
            reason=None,
            now=datetime.now(tz=UTC),
        )
        assert p.status is FandomProposalStatus.REJECTED
        assert p.decision_comment is None
