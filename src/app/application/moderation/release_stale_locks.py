"""Use case: снять протухшие lock'и в moderation_queue.

Предназначен для scheduler'а (будет включён в этапе 4+) и для ручного
админского /release_stale_locks.
"""

from __future__ import annotations

from app.application.moderation.ports import IModerationRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock


class ReleaseStaleLocksUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._moderation = moderation
        self._clock = clock

    async def __call__(self) -> int:
        async with self._uow:
            released = await self._moderation.release_stale_locks(now=self._clock.now())
            await self._uow.commit()
        return released
