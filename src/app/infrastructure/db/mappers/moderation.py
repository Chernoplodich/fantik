"""Мапперы ModerationCase ↔ ORM и ModerationReason ↔ ORM."""

from __future__ import annotations

from app.domain.fanfics.value_objects import MqDecision, MqKind
from app.domain.moderation.entities import ModerationCase
from app.domain.moderation.value_objects import ReasonCode, RejectionReason
from app.domain.shared.types import (
    ChapterId,
    FanficId,
    ModerationCaseId,
    ModerationReasonId,
    UserId,
)
from app.infrastructure.db.models.moderation_queue import ModerationQueue as MQModel
from app.infrastructure.db.models.moderation_reason import (
    ModerationReason as ReasonModel,
)


def mq_to_domain(m: MQModel) -> ModerationCase:
    return ModerationCase(
        id=ModerationCaseId(m.id),
        fic_id=FanficId(m.fic_id),
        chapter_id=ChapterId(m.chapter_id) if m.chapter_id is not None else None,
        kind=MqKind(m.kind),
        submitted_by=UserId(m.submitted_by),
        submitted_at=m.submitted_at,
        locked_by=UserId(m.locked_by) if m.locked_by is not None else None,
        locked_until=m.locked_until,
        decision=MqDecision(m.decision) if m.decision is not None else None,
        decision_reason_ids=list(m.decision_reason_ids or []),
        decision_comment=m.decision_comment,
        decision_comment_entities=list(m.decision_comment_entities or []),
        decided_by=UserId(m.decided_by) if m.decided_by is not None else None,
        decided_at=m.decided_at,
        cancelled_at=m.cancelled_at,
    )


def apply_mq_to_model(m: MQModel, e: ModerationCase) -> None:
    m.fic_id = int(e.fic_id)
    m.chapter_id = int(e.chapter_id) if e.chapter_id is not None else None
    m.kind = e.kind
    m.submitted_by = int(e.submitted_by)
    m.submitted_at = e.submitted_at
    m.locked_by = int(e.locked_by) if e.locked_by is not None else None
    m.locked_until = e.locked_until
    m.decision = e.decision
    m.decision_reason_ids = list(e.decision_reason_ids)
    m.decision_comment = e.decision_comment
    m.decision_comment_entities = list(e.decision_comment_entities)
    m.decided_by = int(e.decided_by) if e.decided_by is not None else None
    m.decided_at = e.decided_at
    m.cancelled_at = e.cancelled_at


def reason_to_domain(m: ReasonModel) -> RejectionReason:
    return RejectionReason(
        id=ModerationReasonId(m.id),
        code=ReasonCode(m.code),
        title=m.title,
        description=m.description,
        sort_order=int(m.sort_order),
        active=bool(m.active),
    )
