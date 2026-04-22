"""FanficVersionRepository: snapshots на submit."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fanfics.ports import IFanficVersionRepository
from app.domain.shared.types import FanficId, FanficVersionId
from app.infrastructure.db.models.fanfic_version import (
    FanficVersion as FanficVersionModel,
)


class FanficVersionRepository(IFanficVersionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def next_version_no(self, fic_id: FanficId) -> int:
        stmt = select(func.coalesce(func.max(FanficVersionModel.version_no), 0)).where(
            FanficVersionModel.fic_id == int(fic_id)
        )
        cur = int((await self._s.execute(stmt)).scalar_one())
        return cur + 1

    async def get_latest_id(self, fic_id: FanficId) -> FanficVersionId | None:
        stmt = (
            select(FanficVersionModel.id)
            .where(FanficVersionModel.fic_id == int(fic_id))
            .order_by(FanficVersionModel.version_no.desc())
            .limit(1)
        )
        val = (await self._s.execute(stmt)).scalar_one_or_none()
        return FanficVersionId(val) if val is not None else None

    async def create_snapshot(
        self,
        *,
        fic_id: FanficId,
        version_no: int,
        title: str,
        summary: str,
        summary_entities: list[dict[str, Any]],
        snapshot_chapters: list[dict[str, Any]],
        now: datetime,
    ) -> FanficVersionId:
        m = FanficVersionModel(
            fic_id=int(fic_id),
            version_no=version_no,
            title=title,
            summary=summary,
            summary_entities=list(summary_entities),
            snapshot_chapters=list(snapshot_chapters),
            created_at=now,
        )
        self._s.add(m)
        await self._s.flush()
        return FanficVersionId(int(m.id))
