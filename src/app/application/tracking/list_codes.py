"""Use case: список трекинг-кодов админа."""

from __future__ import annotations

from app.application.tracking.ports import ITrackingRepository
from app.domain.tracking.entities import TrackingCode


class ListTrackingCodesUseCase:
    def __init__(self, tracking: ITrackingRepository) -> None:
        self._tracking = tracking

    async def __call__(self, *, active_only: bool = False) -> list[TrackingCode]:
        return await self._tracking.list_codes(active_only=active_only)
