"""Доменные события жалоб."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.domain.reports.value_objects import ReportDecision, ReportTarget
from app.domain.shared.events import DomainEvent
from app.domain.shared.types import ReportId, UserId


@dataclass(frozen=True, kw_only=True)
class ReportSubmitted(DomainEvent):
    report_id: ReportId
    reporter_id: UserId
    target_type: ReportTarget
    target_id: int
    name: ClassVar[str] = "report.created"


@dataclass(frozen=True, kw_only=True)
class ReportHandled(DomainEvent):
    report_id: ReportId
    reporter_id: UserId
    target_type: ReportTarget
    target_id: int
    decision: ReportDecision
    notify_reporter: bool
    name: ClassVar[str] = "report.handled"
