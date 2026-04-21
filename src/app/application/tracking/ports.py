"""Порты домена трекинга."""

from __future__ import annotations

from typing import Protocol

from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.tracking.entities import TrackingCode, TrackingEvent


class ITrackingRepository(Protocol):
    async def get_code_id(self, code: str) -> TrackingCodeId | None: ...

    async def get_code(self, code_id: TrackingCodeId) -> TrackingCode | None: ...

    async def list_codes(self, *, active_only: bool = False) -> list[TrackingCode]: ...

    async def save_code(self, code: TrackingCode) -> TrackingCode: ...

    async def record(self, event: TrackingEvent) -> None: ...

    async def has_event_for_user(
        self,
        user_id: UserId,
        event_type: str,
    ) -> bool: ...
