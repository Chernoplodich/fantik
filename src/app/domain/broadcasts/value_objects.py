"""Value-объекты рассылок: статусы и сегменты."""

from __future__ import annotations

from enum import StrEnum


class BroadcastStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    FAILED = "failed"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


# Терминальные статусы — дальше переходов нет.
FINAL_STATUSES: frozenset[BroadcastStatus] = frozenset(
    {BroadcastStatus.FINISHED, BroadcastStatus.CANCELLED, BroadcastStatus.FAILED}
)

FINAL_DELIVERY_STATUSES: frozenset[DeliveryStatus] = frozenset(
    {DeliveryStatus.SENT, DeliveryStatus.BLOCKED}
)


# Известные виды сегментов — валидируются в segment.interpret_segment.
SEGMENT_KIND_ALL = "all"
SEGMENT_KIND_ACTIVE_SINCE_DAYS = "active_since_days"
SEGMENT_KIND_AUTHORS = "authors"
SEGMENT_KIND_SUBSCRIBERS_OF = "subscribers_of"
SEGMENT_KIND_UTM = "utm"
SEGMENT_KIND_RETRY_FAILED = "retry_failed"
