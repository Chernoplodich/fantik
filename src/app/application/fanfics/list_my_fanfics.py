"""Use case: список моих работ для menu:my_works."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import FanficListItem, IFanficRepository
from app.domain.shared.types import UserId


@dataclass(frozen=True, kw_only=True)
class ListMyFanficsCommand:
    author_id: int
    limit: int = 10
    offset: int = 0


@dataclass(frozen=True, kw_only=True)
class ListMyFanficsResult:
    items: list[FanficListItem]
    total: int


class ListMyFanficsUseCase:
    def __init__(self, fanfics: IFanficRepository) -> None:
        self._fanfics = fanfics

    async def __call__(self, cmd: ListMyFanficsCommand) -> ListMyFanficsResult:
        items, total = await self._fanfics.list_by_author_paginated(
            author_id=UserId(cmd.author_id),
            limit=cmd.limit,
            offset=cmd.offset,
        )
        return ListMyFanficsResult(items=items, total=total)
