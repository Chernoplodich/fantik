"""Use case: задать segment_spec рассылки (валидируется через domain.segment)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.broadcasts.ports import IBroadcastRepository
from app.application.shared.ports import UnitOfWork
from app.core.errors import NotFoundError
from app.domain.broadcasts.segment import interpret_segment
from app.domain.shared.types import BroadcastId


@dataclass(frozen=True, kw_only=True)
class SetSegmentCommand:
    broadcast_id: int
    spec: dict[str, Any]


class SetSegmentUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        broadcasts: IBroadcastRepository,
    ) -> None:
        self._uow = uow
        self._broadcasts = broadcasts

    async def __call__(self, cmd: SetSegmentCommand) -> None:
        # Валидируем spec перед открытием транзакции.
        interpret_segment(cmd.spec)
        async with self._uow:
            bc = await self._broadcasts.get(BroadcastId(int(cmd.broadcast_id)))
            if bc is None:
                raise NotFoundError("Рассылка не найдена.")
            bc.set_segment(cmd.spec)
            await self._broadcasts.save(bc)
            await self._uow.commit()
