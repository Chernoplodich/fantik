"""Use case: список активных причин отказа (для multi-select в UI)."""

from __future__ import annotations

from app.application.moderation.ports import IReasonRepository
from app.domain.moderation.value_objects import RejectionReason


class ListReasonsUseCase:
    def __init__(self, reasons: IReasonRepository) -> None:
        self._reasons = reasons

    async def __call__(self) -> list[RejectionReason]:
        return await self._reasons.list_active()
