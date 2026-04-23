"""ReportRepository: жалобы."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reports.ports import IReportRepository, ReportListItem
from app.domain.reports.entities import Report as ReportEntity
from app.domain.reports.value_objects import ReportStatus, ReportTarget
from app.domain.shared.types import ReportId, UserId
from app.infrastructure.db.models.report import Report as ReportModel


def _to_entity(m: ReportModel) -> ReportEntity:
    return ReportEntity(
        id=ReportId(int(m.id)),
        reporter_id=UserId(int(m.reporter_id)),
        target_type=ReportTarget(m.target_type),
        target_id=int(m.target_id),
        reason_code=m.reason_code,
        text=m.text,
        text_entities=list(m.text_entities or []),
        status=ReportStatus(m.status),
        handled_by=UserId(int(m.handled_by)) if m.handled_by is not None else None,
        handled_at=m.handled_at,
        handler_comment=m.handler_comment,
        notify_reporter=bool(m.notify_reporter),
        created_at=m.created_at,
    )


_TEXT_PREVIEW_LEN = 120


class ReportRepository(IReportRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

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
    ) -> ReportEntity:
        m = ReportModel(
            reporter_id=int(reporter_id),
            target_type=target_type,
            target_id=int(target_id),
            reason_code=reason_code,
            text=text,
            text_entities=list(text_entities),
            status=ReportStatus.OPEN,
            notify_reporter=notify_reporter,
            created_at=now,
        )
        self._s.add(m)
        await self._s.flush()
        return _to_entity(m)

    async def get(self, report_id: ReportId) -> ReportEntity | None:
        m = await self._s.get(ReportModel, int(report_id))
        return _to_entity(m) if m else None

    async def save(self, report: ReportEntity) -> None:
        stmt = (
            update(ReportModel)
            .where(ReportModel.id == int(report.id))
            .values(
                status=report.status,
                handled_by=int(report.handled_by) if report.handled_by else None,
                handled_at=report.handled_at,
                handler_comment=report.handler_comment,
                notify_reporter=bool(report.notify_reporter),
            )
        )
        await self._s.execute(stmt)
        await self._s.flush()

    async def exists_open_from_reporter(
        self,
        *,
        reporter_id: UserId,
        target_type: ReportTarget,
        target_id: int,
    ) -> ReportId | None:
        stmt = (
            select(ReportModel.id)
            .where(
                ReportModel.reporter_id == int(reporter_id),
                ReportModel.target_type == target_type,
                ReportModel.target_id == int(target_id),
                ReportModel.status == ReportStatus.OPEN,
            )
            .limit(1)
        )
        rid = (await self._s.execute(stmt)).scalar_one_or_none()
        return ReportId(int(rid)) if rid is not None else None

    async def list_open(self, *, limit: int, offset: int) -> tuple[list[ReportListItem], int]:
        data_stmt = (
            select(ReportModel)
            .where(ReportModel.status == ReportStatus.OPEN)
            .order_by(ReportModel.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        rows: list[ReportModel] = list((await self._s.execute(data_stmt)).scalars().all())
        total_stmt = (
            select(func.count())
            .select_from(ReportModel)
            .where(ReportModel.status == ReportStatus.OPEN)
        )
        total = int((await self._s.execute(total_stmt)).scalar_one())
        items = [
            ReportListItem(
                id=ReportId(int(r.id)),
                reporter_id=UserId(int(r.reporter_id)),
                target_type=ReportTarget(r.target_type),
                target_id=int(r.target_id),
                reason_code=r.reason_code,
                text_preview=_preview(r.text),
                created_at=r.created_at,
            )
            for r in rows
        ]
        return items, total


def _preview(text: str | None) -> str:
    if not text:
        return ""
    t = text.strip().replace("\n", " ")
    if len(t) <= _TEXT_PREVIEW_LEN:
        return t
    return t[: _TEXT_PREVIEW_LEN - 1] + "…"
