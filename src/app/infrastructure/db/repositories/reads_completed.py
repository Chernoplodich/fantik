"""ReadsCompletedRepository: отметки о дочитанных главах."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reading.ports import IReadsCompletedRepository
from app.domain.shared.types import ChapterId, UserId
from app.infrastructure.db.models.read_completed import (
    ReadCompleted as ReadCompletedModel,
)


class ReadsCompletedRepository(IReadsCompletedRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def exists(self, user_id: UserId, chapter_id: ChapterId) -> bool:
        stmt = select(ReadCompletedModel.user_id).where(
            ReadCompletedModel.user_id == int(user_id),
            ReadCompletedModel.chapter_id == int(chapter_id),
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return row is not None

    async def upsert(self, user_id: UserId, chapter_id: ChapterId, now: datetime) -> bool:
        stmt = (
            pg_insert(ReadCompletedModel)
            .values(
                user_id=int(user_id),
                chapter_id=int(chapter_id),
                completed_at=now,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "chapter_id"])
        )
        result = await self._s.execute(stmt)
        await self._s.flush()
        return int(result.rowcount or 0) > 0  # type: ignore[attr-defined]
