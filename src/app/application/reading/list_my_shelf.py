"""Use case: «Моя полка» — недавние, закладки, лайки."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.fanfics.ports import IFanficRepository
from app.application.reading.ports import (
    IBookmarksRepository,
    ILikesRepository,
    IReadingProgressRepository,
    ShelfItem,
)
from app.domain.shared.types import FanficId, UserId


class ShelfKind(StrEnum):
    RECENT = "recent"
    BOOKMARKS = "bookmarks"
    LIKES = "likes"


@dataclass(frozen=True, kw_only=True)
class ListMyShelfCommand:
    user_id: int
    kind: ShelfKind
    limit: int = 20
    offset: int = 0


class ListMyShelfUseCase:
    def __init__(
        self,
        fanfics: IFanficRepository,
        bookmarks: IBookmarksRepository,
        likes: ILikesRepository,
        progress: IReadingProgressRepository,
    ) -> None:
        self._fanfics = fanfics
        self._bookmarks = bookmarks
        self._likes = likes
        self._progress = progress

    async def __call__(self, cmd: ListMyShelfCommand) -> list[ShelfItem]:
        user_id = UserId(cmd.user_id)
        if cmd.kind == ShelfKind.RECENT:
            return await self._build_recent(user_id, cmd.limit)
        fic_ids: list[FanficId]
        if cmd.kind == ShelfKind.BOOKMARKS:
            fic_ids = await self._bookmarks.list_by_user(user_id, cmd.limit, cmd.offset)
        else:
            fic_ids = await self._likes.list_by_user(user_id, cmd.limit, cmd.offset)
        return await self._titles(fic_ids)

    async def _build_recent(self, user_id: UserId, limit: int) -> list[ShelfItem]:
        rows = await self._progress.list_recent(user_id, limit)
        out: list[ShelfItem] = []
        for row in rows:
            fic = await self._fanfics.get(row.fic_id)
            if fic is None:
                continue
            out.append(
                ShelfItem(
                    fic_id=row.fic_id,
                    title=str(fic.title),
                    chapter_id=row.chapter_id,
                    chapter_number=None,
                    page_no=row.page_no,
                    updated_at=row.updated_at,
                )
            )
        return out

    async def _titles(self, fic_ids: list[FanficId]) -> list[ShelfItem]:
        out: list[ShelfItem] = []
        for fid in fic_ids:
            fic = await self._fanfics.get(fid)
            if fic is None:
                continue
            out.append(
                ShelfItem(
                    fic_id=fid,
                    title=str(fic.title),
                    chapter_id=None,
                    chapter_number=None,
                    page_no=None,
                    updated_at=fic.updated_at,
                )
            )
        return out
