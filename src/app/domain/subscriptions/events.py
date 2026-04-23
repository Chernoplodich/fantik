"""Доменные события подписок."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.domain.shared.events import DomainEvent
from app.domain.shared.types import UserId


@dataclass(frozen=True, kw_only=True)
class UserSubscribedToAuthor(DomainEvent):
    subscriber_id: UserId
    author_id: UserId
    name: ClassVar[str] = "subscription.created"


@dataclass(frozen=True, kw_only=True)
class UserUnsubscribedFromAuthor(DomainEvent):
    subscriber_id: UserId
    author_id: UserId
    name: ClassVar[str] = "subscription.removed"
