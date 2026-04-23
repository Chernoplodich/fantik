"""Use case: отменить подачу фика на модерацию.

Правило: отмена запрещена, если модератор уже забрал карточку (lock активен).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.moderation.ports import IModerationRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import ForbiddenActionError
from app.domain.fanfics.value_objects import FicStatus
from app.domain.moderation.exceptions import CaseBeingReviewedError
from app.domain.shared.types import FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class CancelSubmissionCommand:
    fic_id: int
    author_id: int


class CancelSubmissionUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        moderation: IModerationRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._chapters = chapters
        self._moderation = moderation
        self._clock = clock

    async def __call__(self, cmd: CancelSubmissionCommand) -> None:
        now = self._clock.now()
        async with self._uow:
            fic = await self._fanfics.get(FanficId(cmd.fic_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            if fic.author_id != UserId(cmd.author_id):
                raise ForbiddenActionError("Нельзя отменять чужую подачу.")

            case = await self._moderation.get_open_by_fic(fic.id)
            if case is None:
                raise NotFoundError("Открытое задание на модерацию не найдено.")
            if case.is_locked(now=now):
                raise CaseBeingReviewedError("Работу уже смотрит модератор. Попробуй позже.")

            # перевод глав pending → draft
            pending_chapters = await self._chapters.list_by_fic_and_statuses(
                fic.id, [FicStatus.PENDING]
            )
            for ch in pending_chapters:
                ch.mark_draft(now=now)
                await self._chapters.save(ch)

            case.cancel(now=now)
            await self._moderation.mark_cancelled(case_id=case.id, now=now)

            fic.cancel_submission(now=now)
            await self._fanfics.save(fic)

            self._uow.record_events(fic.pull_events() + case.pull_events())
            await self._uow.commit()
