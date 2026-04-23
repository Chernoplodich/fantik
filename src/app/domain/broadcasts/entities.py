"""Агрегат Broadcast со state-machine.

Переходы:
    draft     → scheduled | running | cancelled
    scheduled → running   | cancelled
    running   → finished  | cancelled | failed
    terminal: finished, cancelled, failed — дальше переходов нет.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.broadcasts.events import (
    BroadcastCancelled,
    BroadcastCreated,
    BroadcastFinished,
    BroadcastLaunched,
    BroadcastScheduled,
)
from app.domain.broadcasts.exceptions import InvalidBroadcastTransitionError
from app.domain.broadcasts.value_objects import FINAL_STATUSES, BroadcastStatus
from app.domain.shared.events import EventEmitter
from app.domain.shared.types import BroadcastId, UserId


@dataclass
class Broadcast(EventEmitter):
    id: BroadcastId
    created_by: UserId
    source_chat_id: int
    source_message_id: int
    keyboard: list[list[dict[str, Any]]] | None = None
    segment_spec: dict[str, Any] = field(default_factory=dict)
    scheduled_at: datetime | None = None
    status: BroadcastStatus = BroadcastStatus.DRAFT
    stats: dict[str, int] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        EventEmitter.__init__(self)

    # ---------- фабрики ----------

    @classmethod
    def new_draft(
        cls,
        *,
        broadcast_id: BroadcastId,
        created_by: UserId,
        source_chat_id: int,
        source_message_id: int,
        now: datetime,
    ) -> Broadcast:
        bc = cls(
            id=broadcast_id,
            created_by=created_by,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            created_at=now,
        )
        bc._emit(BroadcastCreated(broadcast_id=bc.id, created_by=bc.created_by))
        return bc

    # ---------- переходы ----------

    def set_keyboard(self, keyboard: list[list[dict[str, Any]]] | None) -> None:
        self._require_status({BroadcastStatus.DRAFT})
        self.keyboard = keyboard

    def set_segment(self, spec: dict[str, Any]) -> None:
        self._require_status({BroadcastStatus.DRAFT})
        self.segment_spec = dict(spec)

    def schedule(self, *, scheduled_at: datetime) -> None:
        self._require_status({BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED})
        self.status = BroadcastStatus.SCHEDULED
        self.scheduled_at = scheduled_at
        self._emit(
            BroadcastScheduled(broadcast_id=self.id, scheduled_at=scheduled_at)
        )

    def launch(self, *, now: datetime) -> None:
        self._require_status({BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED})
        self.status = BroadcastStatus.RUNNING
        self.started_at = now
        self._emit(BroadcastLaunched(broadcast_id=self.id))

    def mark_running(self, *, now: datetime) -> None:
        """Атомарный переход scheduled → running (вызывается scheduler'ом)."""
        self._require_status({BroadcastStatus.SCHEDULED})
        self.status = BroadcastStatus.RUNNING
        self.started_at = now
        self._emit(BroadcastLaunched(broadcast_id=self.id))

    def cancel(self, *, actor_id: UserId | None, now: datetime) -> None:
        if self.status in FINAL_STATUSES:
            raise InvalidBroadcastTransitionError(
                f"Рассылка уже в финальном статусе {self.status.value}."
            )
        self.status = BroadcastStatus.CANCELLED
        self.finished_at = now
        self._emit(
            BroadcastCancelled(broadcast_id=self.id, actor_id=actor_id)
        )

    def mark_finished(self, *, stats: dict[str, int], now: datetime) -> None:
        self._require_status({BroadcastStatus.RUNNING})
        self.status = BroadcastStatus.FINISHED
        self.stats = dict(stats)
        self.finished_at = now
        self._emit(
            BroadcastFinished(
                broadcast_id=self.id,
                total=int(stats.get("total", 0)),
                sent=int(stats.get("sent", 0)),
                failed=int(stats.get("failed", 0)),
                blocked=int(stats.get("blocked", 0)),
            )
        )

    def mark_failed(self, *, now: datetime) -> None:
        self._require_status({BroadcastStatus.RUNNING})
        self.status = BroadcastStatus.FAILED
        self.finished_at = now

    # ---------- helpers ----------

    @property
    def is_terminal(self) -> bool:
        return self.status in FINAL_STATUSES

    def _require_status(self, allowed: set[BroadcastStatus]) -> None:
        if self.status not in allowed:
            raise InvalidBroadcastTransitionError(
                f"Недопустимый переход из {self.status.value}: "
                f"ожидалось одно из {sorted(s.value for s in allowed)}."
            )
