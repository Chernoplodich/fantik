"""Use case: список открытых жалоб (для модератора)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.reports.ports import IReportRepository, ReportListItem


@dataclass(frozen=True, kw_only=True)
class ListOpenReportsCommand:
    limit: int = 10
    offset: int = 0


@dataclass(frozen=True, kw_only=True)
class ListOpenReportsResult:
    items: list[ReportListItem]
    total: int


class ListOpenReportsUseCase:
    def __init__(self, reports: IReportRepository) -> None:
        self._reports = reports

    async def __call__(self, cmd: ListOpenReportsCommand) -> ListOpenReportsResult:
        items, total = await self._reports.list_open(limit=cmd.limit, offset=cmd.offset)
        return ListOpenReportsResult(items=items, total=total)
