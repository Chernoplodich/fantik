"""Порты application-слоя для жалоб."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.reports.entities import Report
from app.domain.reports.value_objects import ReportTarget
from app.domain.shared.types import ReportId, UserId


@dataclass(frozen=True, kw_only=True)
class ReportListItem:
    """DTO для списка открытых жалоб в UI модератора."""

    id: ReportId
    reporter_id: UserId
    target_type: ReportTarget
    target_id: int
    reason_code: str | None
    text_preview: str  # первые 120 символов
    created_at: datetime


class IReportRepository(Protocol):
    async def create(
        self,
        *,
        reporter_id: UserId,
        target_type: ReportTarget,
        target_id: int,
        reason_code: str | None,
        text: str | None,
        text_entities: list[dict[str, object]],
        notify_reporter: bool,
        now: datetime,
    ) -> Report: ...

    async def get(self, report_id: ReportId) -> Report | None: ...

    async def save(self, report: Report) -> None: ...

    async def exists_open_from_reporter(
        self,
        *,
        reporter_id: UserId,
        target_type: ReportTarget,
        target_id: int,
    ) -> ReportId | None:
        """Если у репортера уже есть open-жалоба на ту же цель — вернуть id, иначе None."""
        ...

    async def list_open(self, *, limit: int, offset: int) -> tuple[list[ReportListItem], int]:
        """DTO-список + total count открытых."""
        ...
