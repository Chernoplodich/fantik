"""Кэш ролей в Redis: быстрый RBAC-check в middleware."""

from __future__ import annotations

from redis.asyncio import Redis

_TTL_SECONDS = 60


class RoleCache:
    """TTL-кэш ролей. Ключ: `user_role:{tg_id}`."""

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    @staticmethod
    def _key(tg_id: int) -> str:
        return f"user_role:{tg_id}"

    async def get(self, tg_id: int) -> str | None:
        val = await self._r.get(self._key(tg_id))
        return val.decode() if val else None

    async def set(self, tg_id: int, role: str) -> None:
        await self._r.setex(self._key(tg_id), _TTL_SECONDS, role.encode())

    async def invalidate(self, tg_id: int) -> None:
        await self._r.delete(self._key(tg_id))
