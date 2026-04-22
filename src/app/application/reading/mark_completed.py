"""Use case: отметить главу/фик дочитанной."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import (
    IChapterRepository,
    IFanficRepository,
    IOutboxRepository,
)
from app.application.reading.ports import IReadsCompletedRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class MarkCompletedCommand:
    user_id: int
    fic_id: int
    chapter_id: int


@dataclass(frozen=True, kw_only=True)
class MarkCompletedResult:
    fic_completed: bool  # инкрементнули fanfics.reads_completed_count?
    chapter_completed: bool  # вставили reads_completed?


class MarkCompletedUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        reads_completed: IReadsCompletedRepository,
        outbox: IOutboxRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._chapters = chapters
        self._reads_completed = reads_completed
        self._outbox = outbox
        self._clock = clock

    async def __call__(self, cmd: MarkCompletedCommand) -> MarkCompletedResult:
        user_id = UserId(cmd.user_id)
        fic_id = FanficId(cmd.fic_id)
        ch_id = ChapterId(cmd.chapter_id)
        now = self._clock.now()

        async with self._uow:
            fic = await self._fanfics.get(fic_id)
            if fic is None or fic.status != FicStatus.APPROVED:
                raise NotFoundError("Фик недоступен.")
            chapter = await self._chapters.get(ch_id)
            if chapter is None or chapter.fic_id != fic_id:
                raise NotFoundError("Глава не найдена.")

            # Определяем, последняя ли глава из одобренных.
            approved = [
                c
                for c in await self._chapters.list_by_fic(fic_id)
                if c.status == FicStatus.APPROVED
            ]
            approved.sort(key=lambda c: int(c.number))
            is_last = bool(approved) and int(approved[-1].id) == int(chapter.id)

            inserted = await self._reads_completed.upsert(user_id, ch_id, now)
            fic_completed = False
            if is_last and inserted:
                await self._fanfics.increment_reads_completed(fic_id)
                await self._outbox.append(
                    event_type="fanfic.read_completed",
                    payload={
                        "fic_id": int(fic_id),
                        "user_id": int(user_id),
                        "chapter_id": int(ch_id),
                    },
                    now=now,
                )
                fic_completed = True

            await self._uow.commit()

        return MarkCompletedResult(fic_completed=fic_completed, chapter_completed=inserted)
