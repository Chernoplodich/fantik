"""ReadingProgressRepository: курсор чтения по (user, fic)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reading.ports import (
    IReadingProgressRepository,
    ReadingProgressDTO,
)
from app.domain.shared.types import ChapterId, FanficId, UserId
from app.infrastructure.db.models.reading_progress import (
    ReadingProgress as ReadingProgressModel,
)


def _row_to_dto(m: ReadingProgressModel) -> ReadingProgressDTO:
    return ReadingProgressDTO(
        user_id=UserId(int(m.user_id)),
        fic_id=FanficId(int(m.fic_id)),
        chapter_id=ChapterId(int(m.chapter_id)),
        page_no=int(m.page_no),
        updated_at=m.updated_at,
    )


class ReadingProgressRepository(IReadingProgressRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(
        self,
        *,
        user_id: UserId,
        fic_id: FanficId,
        chapter_id: ChapterId,
        page_no: int,
        now: datetime,
    ) -> None:
        stmt = (
            pg_insert(ReadingProgressModel)
            .values(
                user_id=int(user_id),
                fic_id=int(fic_id),
                chapter_id=int(chapter_id),
                page_no=int(page_no),
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "fic_id"],
                set_={
                    "chapter_id": int(chapter_id),
                    "page_no": int(page_no),
                    "updated_at": now,
                },
            )
        )
        await self._s.execute(stmt)
        await self._s.flush()

    async def get(self, user_id: UserId, fic_id: FanficId) -> ReadingProgressDTO | None:
        stmt = select(ReadingProgressModel).where(
            ReadingProgressModel.user_id == int(user_id),
            ReadingProgressModel.fic_id == int(fic_id),
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _row_to_dto(row) if row else None

    async def list_recent(self, user_id: UserId, limit: int) -> list[ReadingProgressDTO]:
        stmt = (
            select(ReadingProgressModel)
            .where(ReadingProgressModel.user_id == int(user_id))
            .order_by(ReadingProgressModel.updated_at.desc())
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_row_to_dto(r) for r in rows]
