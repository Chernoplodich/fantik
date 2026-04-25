"""Резолвер получателей рассылки на основе segment_spec.

Возвращает AsyncIterator[list[user_id]] — чанки по 1000 для батчевой
вставки в broadcast_deliveries и постановки deliver_one-задач.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.application.broadcasts.ports import (
    IBroadcastRepository,
    IDeliveryRepository,
    IUserSegmentReader,
)
from app.core.errors import NotFoundError
from app.domain.broadcasts.segment import interpret_segment
from app.domain.broadcasts.value_objects import (
    SEGMENT_KIND_RETRY_FAILED,
    DeliveryStatus,
)
from app.domain.shared.types import BroadcastId, UserId


@dataclass(frozen=True, kw_only=True)
class EnumerateRecipientsCommand:
    broadcast_id: int
    chunk_size: int = 1000


class EnumerateRecipientsUseCase:
    def __init__(
        self,
        broadcasts: IBroadcastRepository,
        deliveries: IDeliveryRepository,
        segments: IUserSegmentReader,
    ) -> None:
        self._broadcasts = broadcasts
        self._deliveries = deliveries
        self._segments = segments

    async def __call__(self, cmd: EnumerateRecipientsCommand) -> AsyncIterator[list[UserId]]:
        bc = await self._broadcasts.get(BroadcastId(int(cmd.broadcast_id)))
        if bc is None:
            raise NotFoundError("Рассылка не найдена.")
        plan = interpret_segment(bc.segment_spec)

        if plan.kind == SEGMENT_KIND_RETRY_FAILED:
            assert plan.parent_broadcast_id is not None
            return self._deliveries.iter_user_ids_by_status(
                broadcast_id=BroadcastId(plan.parent_broadcast_id),
                statuses=[DeliveryStatus.FAILED, DeliveryStatus.PENDING],
                chunk_size=cmd.chunk_size,
            )
        return self._segments.iter_user_ids(plan=plan, chunk_size=cmd.chunk_size)
