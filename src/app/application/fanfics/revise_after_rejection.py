"""Use case: автор нажал «Доработать» после отказа."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IFanficRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import ForbiddenActionError
from app.domain.shared.types import FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class ReviseAfterRejectionCommand:
    fic_id: int
    author_id: int


class ReviseAfterRejectionUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._clock = clock

    async def __call__(self, cmd: ReviseAfterRejectionCommand) -> None:
        now = self._clock.now()
        async with self._uow:
            fic = await self._fanfics.get(FanficId(cmd.fic_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            if fic.author_id != UserId(cmd.author_id):
                raise ForbiddenActionError("Нельзя дорабатывать чужой фик.")
            fic.mark_revising(now=now)
            await self._fanfics.save(fic)
            self._uow.record_events(fic.pull_events())
            await self._uow.commit()
