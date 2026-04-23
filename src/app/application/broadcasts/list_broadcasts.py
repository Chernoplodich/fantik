"""Use case: список рассылок админа + карточка одной."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.broadcasts.ports import (
    IBroadcastRepository,
    IDeliveryRepository,
)
from app.core.errors import NotFoundError
from app.domain.broadcasts.entities import Broadcast
from app.domain.broadcasts.value_objects import DeliveryStatus
from app.domain.shared.types import BroadcastId, UserId


@dataclass(frozen=True, kw_only=True)
class BroadcastCardView:
    broadcast: Broadcast
    counts: dict[DeliveryStatus, int]


class ListMyBroadcastsUseCase:
    def __init__(self, broadcasts: IBroadcastRepository) -> None:
        self._broadcasts = broadcasts

    async def __call__(self, *, created_by: int, limit: int = 20) -> list[Broadcast]:
        return await self._broadcasts.list_by_creator(
            created_by=UserId(int(created_by)), limit=limit
        )


class GetBroadcastCardUseCase:
    def __init__(
        self,
        broadcasts: IBroadcastRepository,
        deliveries: IDeliveryRepository,
    ) -> None:
        self._broadcasts = broadcasts
        self._deliveries = deliveries

    async def __call__(self, broadcast_id: int) -> BroadcastCardView:
        bc = await self._broadcasts.get(BroadcastId(int(broadcast_id)))
        if bc is None:
            raise NotFoundError("Рассылка не найдена.")
        counts = await self._deliveries.count_by_status(bc.id)
        return BroadcastCardView(broadcast=bc, counts=counts)
