"""FanficFeedReader: read-only витрина каталога по partial-индексам approved."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reading.ports import FeedItem, IFanficFeedReader
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FandomId, FanficId, UserId
from app.infrastructure.db.models.fandom import Fandom as FandomModel
from app.infrastructure.db.models.fanfic import Fanfic as FanficModel
from app.infrastructure.db.models.user import User as UserModel


def _row_to_feed(
    fic: FanficModel, author: UserModel | None, fandom: FandomModel | None
) -> FeedItem:
    return FeedItem(
        fic_id=FanficId(int(fic.id)),
        title=fic.title,
        author_id=UserId(int(fic.author_id)),
        author_nick=author.author_nick if author else None,
        fandom_id=FandomId(int(fic.fandom_id)),
        fandom_name=fandom.name if fandom else None,
        chapters_count=int(fic.chapters_count),
        likes_count=int(fic.likes_count),
        reads_completed_count=int(fic.reads_completed_count),
        first_published_at=fic.first_published_at,
    )


class FanficFeedReader(IFanficFeedReader):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_new(
        self, *, limit: int, offset: int, fandom_id: FandomId | None = None
    ) -> list[FeedItem]:
        stmt = (
            select(FanficModel, UserModel, FandomModel)
            .join(UserModel, UserModel.id == FanficModel.author_id)
            .join(FandomModel, FandomModel.id == FanficModel.fandom_id)
            .where(FanficModel.status == FicStatus.APPROVED)
            .order_by(FanficModel.first_published_at.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        if fandom_id is not None:
            stmt = stmt.where(FanficModel.fandom_id == int(fandom_id))
        rows = (await self._s.execute(stmt)).all()
        return [_row_to_feed(fic, author, fandom) for fic, author, fandom in rows]

    async def list_top(
        self, *, limit: int, offset: int, fandom_id: FandomId | None = None
    ) -> list[FeedItem]:
        stmt = (
            select(FanficModel, UserModel, FandomModel)
            .join(UserModel, UserModel.id == FanficModel.author_id)
            .join(FandomModel, FandomModel.id == FanficModel.fandom_id)
            .where(FanficModel.status == FicStatus.APPROVED)
            .order_by(FanficModel.likes_count.desc(), FanficModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if fandom_id is not None:
            stmt = stmt.where(FanficModel.fandom_id == int(fandom_id))
        rows = (await self._s.execute(stmt)).all()
        return [_row_to_feed(fic, author, fandom) for fic, author, fandom in rows]

    async def get_titles(self, fic_ids: list[FanficId]) -> dict[FanficId, str]:
        if not fic_ids:
            return {}
        stmt = select(FanficModel.id, FanficModel.title).where(
            FanficModel.id.in_([int(f) for f in fic_ids])
        )
        rows = (await self._s.execute(stmt)).all()
        return {FanficId(int(fid)): title for fid, title in rows}
