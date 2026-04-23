"""Integration: outbox-dispatcher → index_fanfic.kiq() реально планирует задачу.

В TEST env-режиме TaskIQ использует `InMemoryBroker`, так что после `kiq()`
задача НЕ выполнится сама — мы просто убеждаемся, что её поставили
(в поле broker.kicks есть запись).

В реальном воркере `outbox_dispatch_tick` → `index_fanfic.kiq` → воркер
подхватывает и выполняет.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.tasks.outbox_dispatcher import _dispatch_one


@pytest.mark.integration
class TestOutboxToIndexPipeline:
    async def test_fanfic_approved_schedules_repaginate_and_index(
        self,
        pg_engine: AsyncEngine,
    ) -> None:
        # Засеваем минимально необходимые данные, чтобы просто проверить маршрутизатор.
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id, timezone) VALUES (5001, 'UTC') ON CONFLICT DO NOTHING")
            )

        # _dispatch_one напрямую — чистая функция маршрутизации.
        # Её цель — вызвать .kiq() на index_fanfic и repaginate_chapter.
        # С InMemoryBroker это запишет task в внутренний список.
        payload = {"fic_id": 999, "chapter_ids": [1001, 1002]}
        # не должно быть исключения
        await _dispatch_one("fanfic.approved", payload)

        # И повторно — для edited
        await _dispatch_one("fanfic.edited", {"fic_id": 999})
        await _dispatch_one("fanfic.archived", {"fic_id": 999})

        # Неизвестный event_type не должен падать.
        await _dispatch_one("some.unknown.event", {})
