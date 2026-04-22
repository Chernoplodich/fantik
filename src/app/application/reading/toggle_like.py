"""Use case: toggle like (insert + atomic increment / delete + atomic decrement)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IFanficRepository
from app.application.reading.ports import ILikesRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class ToggleLikeCommand:
    user_id: int
    fic_id: int


@dataclass(frozen=True, kw_only=True)
class ToggleLikeResult:
    now_liked: bool


class ToggleLikeUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        likes: ILikesRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._likes = likes
        self._clock = clock

    async def __call__(self, cmd: ToggleLikeCommand) -> ToggleLikeResult:
        user_id = UserId(cmd.user_id)
        fic_id = FanficId(cmd.fic_id)
        now = self._clock.now()

        async with self._uow:
            fic = await self._fanfics.get(fic_id)
            if fic is None or fic.status != FicStatus.APPROVED:
                raise NotFoundError("Фик недоступен.")

            inserted = await self._likes.add(user_id, fic_id, now)
            if inserted:
                await self._fanfics.increment_likes(fic_id)
                await self._uow.commit()
                return ToggleLikeResult(now_liked=True)

            removed = await self._likes.remove(user_id, fic_id)
            if removed:
                await self._fanfics.decrement_likes(fic_id)
            await self._uow.commit()
            return ToggleLikeResult(now_liked=False)
