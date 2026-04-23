"""Глобальный flood-lock на все воркеры рассылки.

При получении `429 Too Many Requests` от Telegram бот блокируется полностью
(не только рассылка — вообще все API-вызовы). Если один воркер поймал 429
и ждёт, остальные не должны продолжать лезть к API: это лишь усугубляет
ban. Поэтому храним в Redis общую «заглушку» — unix-ts когда flood кончится,
и все воркеры (и bot-процесс при send_text) перед каждым TG-запросом её
читают и ждут.

Ключ — `broadcast:flood_until`, TTL = время ожидания (миллисекунды).
"""

from __future__ import annotations

import asyncio
import random

from redis.asyncio import Redis

_KEY = "broadcast:flood_until"


class BroadcastFloodLock:
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def set_flood(self, seconds: float) -> None:
        """Установить блок на N секунд.

        PSETEX перезаписывает существующий TTL — если сейчас 429 с большим
        retry_after, он и должен перекрыть старый.
        """
        ms = max(100, int(seconds * 1000))
        await self._r.set(_KEY, "1", px=ms)

    async def wait_if_blocked(self, *, max_wait: float = 120.0) -> float:
        """Если флаг активен — поспать до его истечения (+ джиттер).

        Возвращает число секунд, которое прождали. `max_wait` — предохранитель
        от бесконечного ожидания (если TTL вернётся > max_wait, всё равно
        спим только max_wait — дальше пусть воркер решит сам).
        """
        pttl = await self._r.pttl(_KEY)
        if pttl is None or pttl <= 0:
            return 0.0
        wait = min(pttl / 1000.0, max_wait) + random.uniform(0.05, 0.3)
        await asyncio.sleep(wait)
        return wait
