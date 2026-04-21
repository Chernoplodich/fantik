"""Доменные сущности трекинга: код кампании и событие."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.shared.types import (
    TrackingCodeId,
    TrackingEventId,
    UserId,
)
from app.domain.tracking.value_objects import TrackingCodeStr, TrackingEventType


@dataclass
class TrackingCode:
    """Рекламная/реферальная кампания."""

    id: TrackingCodeId | None
    code: TrackingCodeStr
    name: str
    description: str | None
    created_by: UserId
    active: bool
    created_at: datetime | None


@dataclass(frozen=True)
class TrackingEvent:
    """Единичное событие, ассоциированное с пользователем и (опц.) источником."""

    id: TrackingEventId | None
    code_id: TrackingCodeId | None
    user_id: UserId
    event_type: TrackingEventType
    payload: dict[str, Any]
    created_at: datetime | None
