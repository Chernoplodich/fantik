"""OutboxRepository: append-only очередь событий."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fanfics.ports import IOutboxRepository
from app.domain.shared.types import OutboxId
from app.infrastructure.db.models.outbox import Outbox as OutboxModel


class OutboxRepository(IOutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def append(
        self, *, event_type: str, payload: dict[str, Any], now: datetime
    ) -> OutboxId:
        m = OutboxModel(
            event_type=event_type,
            payload=dict(payload),
            created_at=now,
        )
        self._s.add(m)
        await self._s.flush()
        return OutboxId(int(m.id))
