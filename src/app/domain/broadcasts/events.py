"""Доменные события жизненного цикла рассылки."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from app.domain.shared.events import DomainEvent
from app.domain.shared.types import BroadcastId, UserId


@dataclass(frozen=True, kw_only=True)
class BroadcastCreated(DomainEvent):
    broadcast_id: BroadcastId
    created_by: UserId

    name: ClassVar[str] = "broadcast.created"


@dataclass(frozen=True, kw_only=True)
class BroadcastScheduled(DomainEvent):
    broadcast_id: BroadcastId
    scheduled_at: datetime

    name: ClassVar[str] = "broadcast.scheduled"


@dataclass(frozen=True, kw_only=True)
class BroadcastLaunched(DomainEvent):
    broadcast_id: BroadcastId

    name: ClassVar[str] = "broadcast.launched"


@dataclass(frozen=True, kw_only=True)
class BroadcastCancelled(DomainEvent):
    broadcast_id: BroadcastId
    actor_id: UserId | None

    name: ClassVar[str] = "broadcast.cancelled"


@dataclass(frozen=True, kw_only=True)
class BroadcastFinished(DomainEvent):
    broadcast_id: BroadcastId
    total: int
    sent: int
    failed: int
    blocked: int

    name: ClassVar[str] = "broadcast.finished"
