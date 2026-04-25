"""Доменные события заявок на фандом.

Используются для аудит-лога и для уведомления автора (через application-слой).
В отличие от outbox-флоу подписок, эти события публикуются синхронно из
admin-handler'а, поэтому отдельной таблицы outbox для них нет — но event-объект
сохраняем как контрактную структуру.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.reference.value_objects import ProposalId
from app.domain.shared.events import DomainEvent
from app.domain.shared.types import FandomId, UserId


@dataclass(frozen=True, kw_only=True)
class FandomProposalSubmitted(DomainEvent):
    proposal_id: ProposalId
    requested_by: UserId
    proposal_name: str
    category_hint: str


@dataclass(frozen=True, kw_only=True)
class FandomProposalApproved(DomainEvent):
    proposal_id: ProposalId
    requested_by: UserId
    proposal_name: str
    fandom_id: FandomId


@dataclass(frozen=True, kw_only=True)
class FandomProposalRejected(DomainEvent):
    proposal_id: ProposalId
    requested_by: UserId
    proposal_name: str
    reason: str | None
