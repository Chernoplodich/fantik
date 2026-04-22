"""RedisProgressThrottle: SET NX EX 5 для ограничения частоты записей прогресса.

Ключ включает chapter_id, чтобы смена главы всегда создавала новую throttle-
запись — это гарантирует, что первая запись в новой главе проходит сразу.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.application.reading.ports import IProgressThrottle
from app.domain.shared.types import ChapterId, FanficId, UserId

_WINDOW_SECONDS = 5
_KEY_PREFIX = "progress_throttle"


class RedisProgressThrottle(IProgressThrottle):
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    @staticmethod
    def _key(user_id: UserId, fic_id: FanficId, chapter_id: ChapterId) -> str:
        return f"{_KEY_PREFIX}:{int(user_id)}:{int(fic_id)}:{int(chapter_id)}"

    async def try_acquire(self, user_id: UserId, fic_id: FanficId, chapter_id: ChapterId) -> bool:
        ok = await self._r.set(
            self._key(user_id, fic_id, chapter_id),
            b"1",
            nx=True,
            ex=_WINDOW_SECONDS,
        )
        return bool(ok)
