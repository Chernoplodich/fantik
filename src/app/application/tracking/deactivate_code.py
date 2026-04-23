"""Use case: деактивировать UTM-код (soft-delete)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.moderation.ports import IAuditLog
from app.application.shared.ports import UnitOfWork
from app.application.tracking.ports import ITrackingRepository
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.shared.types import TrackingCodeId, UserId


@dataclass(frozen=True, kw_only=True)
class DeactivateCodeCommand:
    code_id: int
    actor_id: int


class DeactivateTrackingCodeUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        tracking: ITrackingRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._tracking = tracking
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: DeactivateCodeCommand) -> None:
        async with self._uow:
            code = await self._tracking.get_code(TrackingCodeId(int(cmd.code_id)))
            if code is None:
                raise NotFoundError("Трекинг-код не найден.")
            if not code.active:
                await self._uow.commit()
                return
            code.active = False
            await self._tracking.save_code(code)
            now = self._clock.now()
            await self._audit.log(
                actor_id=UserId(int(cmd.actor_id)),
                action="tracking.deactivate",
                target_type="tracking_code",
                target_id=int(code.id) if code.id else 0,
                payload={"code": str(code.code)},
                now=now,
            )
            await self._uow.commit()
