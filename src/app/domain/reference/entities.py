"""Агрегат FandomProposal — заявка пользователя на добавление нового фандома."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.reference.events import (
    FandomProposalApproved,
    FandomProposalRejected,
)
from app.domain.reference.exceptions import ProposalAlreadyHandledError
from app.domain.reference.value_objects import FandomProposalStatus, ProposalId
from app.domain.shared.events import EventEmitter
from app.domain.shared.types import FandomId, UserId


@dataclass
class FandomProposal(EventEmitter):
    id: ProposalId
    requested_by: UserId
    name: str
    category_hint: str
    comment: str | None = None
    status: FandomProposalStatus = FandomProposalStatus.PENDING
    reviewed_by: UserId | None = None
    reviewed_at: datetime | None = None
    decision_comment: str | None = None
    created_fandom_id: FandomId | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        EventEmitter.__init__(self)

    # ---------- lifecycle ----------

    def approve(
        self,
        *,
        moderator_id: UserId,
        fandom_id: FandomId,
        comment: str | None,
        now: datetime,
    ) -> None:
        self._require_pending()
        self.status = FandomProposalStatus.APPROVED
        self.reviewed_by = moderator_id
        self.reviewed_at = now
        self.decision_comment = comment
        self.created_fandom_id = fandom_id
        self._emit(
            FandomProposalApproved(
                proposal_id=self.id,
                requested_by=self.requested_by,
                proposal_name=self.name,
                fandom_id=fandom_id,
            )
        )

    def reject(
        self,
        *,
        moderator_id: UserId,
        reason: str | None,
        now: datetime,
    ) -> None:
        self._require_pending()
        self.status = FandomProposalStatus.REJECTED
        self.reviewed_by = moderator_id
        self.reviewed_at = now
        self.decision_comment = reason
        self._emit(
            FandomProposalRejected(
                proposal_id=self.id,
                requested_by=self.requested_by,
                proposal_name=self.name,
                reason=reason,
            )
        )

    # ---------- helpers ----------

    def _require_pending(self) -> None:
        if self.status is not FandomProposalStatus.PENDING:
            raise ProposalAlreadyHandledError("Заявка уже обработана.")
