"""Use case: сохранить прогресс чтения (throttled в Redis)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.reading.ports import (
    IProgressThrottle,
    IReadingProgressRepository,
)
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.domain.shared.types import ChapterId, FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class SaveProgressCommand:
    user_id: int
    fic_id: int
    chapter_id: int
    page_no: int


class SaveProgressUseCase:
    """Сохраняем прогресс НЕ чаще одного раза в 5 секунд на (user, fic, chapter).

    Throttle-ключ включает chapter_id: смена главы мгновенно делает запись,
    чтобы курсор «▶ Продолжить» всегда показывал актуальную главу.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        progress: IReadingProgressRepository,
        throttle: IProgressThrottle,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._progress = progress
        self._throttle = throttle
        self._clock = clock

    async def __call__(self, cmd: SaveProgressCommand) -> bool:
        """True — запись выполнена; False — отброшено throttle'ом."""
        user_id = UserId(cmd.user_id)
        fic_id = FanficId(cmd.fic_id)
        chapter_id = ChapterId(cmd.chapter_id)
        if not await self._throttle.try_acquire(user_id, fic_id, chapter_id):
            return False
        now = self._clock.now()
        async with self._uow:
            await self._progress.upsert(
                user_id=user_id,
                fic_id=fic_id,
                chapter_id=chapter_id,
                page_no=cmd.page_no,
                now=now,
            )
            await self._uow.commit()
        return True
