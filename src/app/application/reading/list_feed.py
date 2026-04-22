"""Use case: лента «Новое» / «Топ» (опционально по фэндому)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.reading.ports import FeedItem, IFanficFeedReader
from app.domain.shared.types import FandomId


class FeedKind(StrEnum):
    NEW = "new"
    TOP = "top"


@dataclass(frozen=True, kw_only=True)
class ListFeedCommand:
    kind: FeedKind
    fandom_id: int | None = None
    limit: int = 10
    offset: int = 0


class ListFeedUseCase:
    def __init__(self, feed: IFanficFeedReader) -> None:
        self._feed = feed

    async def __call__(self, cmd: ListFeedCommand) -> list[FeedItem]:
        fandom = FandomId(cmd.fandom_id) if cmd.fandom_id else None
        if cmd.kind == FeedKind.NEW:
            return await self._feed.list_new(limit=cmd.limit, offset=cmd.offset, fandom_id=fandom)
        return await self._feed.list_top(limit=cmd.limit, offset=cmd.offset, fandom_id=fandom)
