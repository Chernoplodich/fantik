"""Use case: воронка по UTM-коду."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.stats.ports import FunnelRow, IStatsReader
from app.core.errors import NotFoundError


@dataclass(frozen=True, kw_only=True)
class GetFunnelCommand:
    code: str
    days: int = 30


class GetFunnelUseCase:
    def __init__(self, reader: IStatsReader) -> None:
        self._reader = reader

    async def __call__(self, cmd: GetFunnelCommand) -> FunnelRow:
        row = await self._reader.funnel_by_code(code=cmd.code, days=cmd.days)
        if row is None:
            raise NotFoundError(f"Трекинг-код «{cmd.code}» не найден.")
        return row
