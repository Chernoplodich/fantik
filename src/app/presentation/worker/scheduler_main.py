"""Entrypoint scheduler'а TaskIQ.

Запускается через `taskiq scheduler app.presentation.worker.scheduler_main:scheduler`.
Импортирует модули задач с labeled schedule, чтобы LabelScheduleSource их видел.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.tasks.broker import scheduler  # noqa: F401

# Регистрация задач с `schedule=[...]` — Label source читает броуза таски.
from app.infrastructure.tasks import outbox_dispatcher  # noqa: F401
from app.infrastructure.tasks import repagination  # noqa: F401

if __name__ == "__main__":
    setup_logging(get_settings())

    async def _idle() -> None:
        while True:
            await asyncio.sleep(60)

    asyncio.run(_idle())
