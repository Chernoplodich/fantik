"""BookmarksRepository: закладки пользователя."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reading.ports import IBookmarksRepository
from app.domain.shared.types import FanficId, UserId
from app.infrastructure.db.models.bookmark import Bookmark as BookmarkModel


class BookmarksRepository(IBookmarksRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def exists(self, user_id: UserId, fic_id: FanficId) -> bool:
        stmt = select(BookmarkModel.user_id).where(
            BookmarkModel.user_id == int(user_id),
            BookmarkModel.fic_id == int(fic_id),
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return row is not None

    async def add(self, user_id: UserId, fic_id: FanficId, now: datetime) -> bool:
        stmt = (
            pg_insert(BookmarkModel)
            .values(user_id=int(user_id), fic_id=int(fic_id), created_at=now)
            .on_conflict_do_nothing(index_elements=["user_id", "fic_id"])
        )
        result = await self._s.execute(stmt)
        await self._s.flush()
        return int(result.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def remove(self, user_id: UserId, fic_id: FanficId) -> bool:
        stmt = delete(BookmarkModel).where(
            BookmarkModel.user_id == int(user_id),
            BookmarkModel.fic_id == int(fic_id),
        )
        result = await self._s.execute(stmt)
        await self._s.flush()
        return int(result.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def list_by_user(self, user_id: UserId, limit: int, offset: int) -> list[FanficId]:
        stmt = (
            select(BookmarkModel.fic_id)
            .where(BookmarkModel.user_id == int(user_id))
            .order_by(BookmarkModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [FanficId(int(r)) for r in rows]
