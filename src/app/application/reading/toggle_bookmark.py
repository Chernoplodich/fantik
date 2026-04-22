"""Use case: toggle bookmark (без счётчика)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IFanficRepository
from app.application.reading.ports import IBookmarksRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class ToggleBookmarkCommand:
    user_id: int
    fic_id: int


@dataclass(frozen=True, kw_only=True)
class ToggleBookmarkResult:
    now_bookmarked: bool


class ToggleBookmarkUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        bookmarks: IBookmarksRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._bookmarks = bookmarks
        self._clock = clock

    async def __call__(self, cmd: ToggleBookmarkCommand) -> ToggleBookmarkResult:
        user_id = UserId(cmd.user_id)
        fic_id = FanficId(cmd.fic_id)
        now = self._clock.now()

        async with self._uow:
            fic = await self._fanfics.get(fic_id)
            if fic is None or fic.status != FicStatus.APPROVED:
                raise NotFoundError("Фик недоступен.")

            inserted = await self._bookmarks.add(user_id, fic_id, now)
            if inserted:
                await self._uow.commit()
                return ToggleBookmarkResult(now_bookmarked=True)

            await self._bookmarks.remove(user_id, fic_id)
            await self._uow.commit()
            return ToggleBookmarkResult(now_bookmarked=False)
