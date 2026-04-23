"""Агрегат Report."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.reports.events import ReportHandled
from app.domain.reports.exceptions import ReportAlreadyHandledError
from app.domain.reports.value_objects import ReportDecision, ReportStatus, ReportTarget
from app.domain.shared.events import EventEmitter
from app.domain.shared.types import ReportId, UserId


@dataclass
class Report(EventEmitter):
    id: ReportId
    reporter_id: UserId
    target_type: ReportTarget
    target_id: int
    reason_code: str | None
    text: str | None
    text_entities: list[dict[str, Any]] = field(default_factory=list)
    status: ReportStatus = ReportStatus.OPEN
    handled_by: UserId | None = None
    handled_at: datetime | None = None
    handler_comment: str | None = None
    notify_reporter: bool = True
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        EventEmitter.__init__(self)

    # ---------- lifecycle ----------

    def dismiss(
        self,
        *,
        moderator_id: UserId,
        comment: str | None,
        now: datetime,
    ) -> None:
        self._require_open()
        self.status = ReportStatus.DISMISSED
        self.handled_by = moderator_id
        self.handled_at = now
        self.handler_comment = comment
        self._emit(
            ReportHandled(
                report_id=self.id,
                reporter_id=self.reporter_id,
                target_type=self.target_type,
                target_id=self.target_id,
                decision=ReportDecision.DISMISS,
                notify_reporter=self.notify_reporter,
            )
        )

    def action(
        self,
        *,
        moderator_id: UserId,
        comment: str | None,
        now: datetime,
    ) -> None:
        self._require_open()
        self.status = ReportStatus.ACTIONED
        self.handled_by = moderator_id
        self.handled_at = now
        self.handler_comment = comment
        self._emit(
            ReportHandled(
                report_id=self.id,
                reporter_id=self.reporter_id,
                target_type=self.target_type,
                target_id=self.target_id,
                decision=ReportDecision.ACTION,
                notify_reporter=self.notify_reporter,
            )
        )

    # ---------- helpers ----------

    def _require_open(self) -> None:
        if self.status != ReportStatus.OPEN:
            raise ReportAlreadyHandledError("Жалоба уже обработана.")
