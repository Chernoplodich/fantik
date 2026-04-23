"""Адаптер ISearchIndexQueue → TaskIQ + Redis-дебаунс.

- `enqueue(fic_id)` — обычная постановка `index_fanfic` в очередь.
- `enqueue_debounced(fic_id, ttl_s=60)` — агрегация «шума» (лайки):
  ключ `search:idx:debounce:{fic_id}` ставится через `SET ... NX EX ttl_s`;
  если ключ создан — задача ставится, иначе — no-op (внутри окна уже есть задача).

Ключ per-fic, не per-user: второй лайк от другого пользователя в те же 60с
тоже должен попасть в следующий индекс-апдейт, а не потеряться.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.application.search.ports import ISearchIndexQueue
from app.core.logging import get_logger
from app.domain.shared.types import FanficId
from app.infrastructure.tasks.indexing import index_fanfic

log = get_logger(__name__)

_DEBOUNCE_KEY = "search:idx:debounce:{fic_id}"


class TaskiqSearchIndexQueue(ISearchIndexQueue):
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def enqueue(self, fic_id: FanficId | int) -> None:
        await index_fanfic.kiq(int(fic_id))

    async def enqueue_debounced(self, fic_id: FanficId | int, ttl_s: int = 60) -> None:
        key = _DEBOUNCE_KEY.format(fic_id=int(fic_id))
        acquired = await self._r.set(key, b"1", nx=True, ex=ttl_s)
        if not acquired:
            log.debug("search_index_debounced", fic_id=int(fic_id), ttl_s=ttl_s)
            return

        await index_fanfic.kiq(int(fic_id))
