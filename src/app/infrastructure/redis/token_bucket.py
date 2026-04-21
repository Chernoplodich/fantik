"""Распределённый token-bucket на Redis Lua-скрипте.

Используется для:
- anti-flood per user (throttle);
- глобального rate-limit рассылок (25 msg/s).

Lua-скрипт атомарен и безопасен при concurrent acquire.
"""

from __future__ import annotations

import asyncio
import time

from redis.asyncio import Redis

_LUA_SCRIPT = """
-- KEYS[1] = bucket key
-- ARGV[1] = rate (tokens per second, float)
-- ARGV[2] = capacity
-- ARGV[3] = now (ms)
-- Возвращает: 1 — токен выдан; отрицательное число — мс ждать.
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = capacity end
if ts == nil then ts = now end
local delta = (now - ts) / 1000 * rate
tokens = math.min(capacity, tokens + delta)
if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
  redis.call('PEXPIRE', KEYS[1], 60000)
  return 1
else
  local wait_ms = math.ceil((1 - tokens) * 1000 / rate)
  redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
  redis.call('PEXPIRE', KEYS[1], 60000)
  return -wait_ms
end
"""


class TokenBucket:
    """Клиент к token-bucket'у, атомарно управляемому на стороне Redis."""

    def __init__(self, redis: Redis) -> None:
        self._r = redis
        self._script = redis.register_script(_LUA_SCRIPT)

    async def try_acquire(self, key: str, rate: float, capacity: int) -> float:
        """Попытаться получить токен. Возвращает 0.0 при успехе
        или положительное число секунд до следующей попытки."""
        result: int = int(
            await self._script(  # type: ignore[misc]
                keys=[key], args=[str(rate), str(capacity), str(int(time.time() * 1000))]
            )
        )
        if result == 1:
            return 0.0
        return -result / 1000.0

    async def acquire(self, key: str, rate: float, capacity: int) -> None:
        """Блокирующий acquire — ждёт, пока токен появится."""
        while True:
            delay = await self.try_acquire(key, rate, capacity)
            if delay == 0.0:
                return
            await asyncio.sleep(delay)
