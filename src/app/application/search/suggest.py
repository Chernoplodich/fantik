"""SuggestUseCase: автодополнение тегов/фандомов/персонажей по префиксу, с кэшем 5 минут."""

from __future__ import annotations

from app.application.search.dto import SuggestCommand
from app.application.search.ports import ISearchCache, ISuggestReader

_TTL_S = 300


class SuggestUseCase:
    def __init__(self, reader: ISuggestReader, cache: ISearchCache) -> None:
        self._reader = reader
        self._cache = cache

    async def __call__(self, cmd: SuggestCommand) -> list[str]:
        prefix = cmd.prefix.strip().lower()
        if not prefix or len(prefix) < 2:
            return []

        key = f"suggest:{cmd.kind}:{prefix}"
        cached = await self._cache.get(key)
        if isinstance(cached, list):
            return [str(x) for x in cached if isinstance(x, str)]

        items = await self._reader.by_prefix(kind=cmd.kind, prefix=prefix, limit=cmd.limit)
        await self._cache.setex(key, _TTL_S, items)
        return items
