"""RedisPageCache: msgpack-кэш страниц главы. Ключ `ch:{chapter_id}:p:{page_no}`."""

from __future__ import annotations

from typing import Any, cast

import msgpack
from redis.asyncio import Redis

from app.application.reading.ports import IPageCache
from app.domain.fanfics.services.paginator import Page
from app.domain.shared.types import ChapterId

_TTL_SECONDS = 3600
_KEY_PREFIX = "ch"


class RedisPageCache(IPageCache):
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    @staticmethod
    def _key(chapter_id: ChapterId | int, page_no: int) -> str:
        return f"{_KEY_PREFIX}:{int(chapter_id)}:p:{page_no}"

    @staticmethod
    def _pattern(chapter_id: ChapterId | int) -> str:
        return f"{_KEY_PREFIX}:{int(chapter_id)}:p:*"

    async def get(self, chapter_id: ChapterId, page_no: int) -> Page | None:
        raw = await self._r.get(self._key(chapter_id, page_no))
        if raw is None:
            return None
        try:
            data = msgpack.unpackb(raw, raw=False)
        except (msgpack.UnpackException, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        d = cast(dict[str, Any], data)
        try:
            return Page(
                page_no=int(d["page_no"]),
                text=str(d["text"]),
                entities=list(d.get("entities") or []),
                chars_count=int(d.get("chars_count", 0)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    async def set(self, chapter_id: ChapterId, page_no: int, page: Page) -> None:
        payload = msgpack.packb(
            {
                "page_no": page.page_no,
                "text": page.text,
                "entities": list(page.entities or []),
                "chars_count": page.chars_count,
            },
            use_bin_type=True,
        )
        await self._r.setex(self._key(chapter_id, page_no), _TTL_SECONDS, payload)

    async def invalidate_chapter(self, chapter_id: ChapterId) -> None:
        pattern = self._pattern(chapter_id)
        # SCAN + UNLINK чтобы не блокировать Redis при большом кол-ве страниц.
        batch: list[bytes | str] = []
        async for key in self._r.scan_iter(match=pattern, count=200):
            batch.append(key)
            if len(batch) >= 200:
                await self._r.unlink(*batch)
                batch.clear()
        if batch:
            await self._r.unlink(*batch)
