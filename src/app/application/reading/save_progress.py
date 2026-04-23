"""Use case: сохранить прогресс чтения.

Upsert-only — всегда фиксируем последнюю страницу пользователя. Throttling
снят: DB-запись на каждый клик «◀/▶» фактически бесплатна (уникальный индекс
на (user_id, fic_id)), зато курсор «▶ Продолжить» всегда актуален.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.reading.ports import IReadingProgressRepository
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
    def __init__(
        self,
        uow: UnitOfWork,
        progress: IReadingProgressRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._progress = progress
        self._clock = clock

    async def __call__(self, cmd: SaveProgressCommand) -> bool:
        """Всегда сохраняем — возвращает True (сохранено)."""
        user_id = UserId(cmd.user_id)
        fic_id = FanficId(cmd.fic_id)
        chapter_id = ChapterId(cmd.chapter_id)
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
