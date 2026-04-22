"""Entrypoint обычного TaskIQ-воркера (default queue).

Запускается через `taskiq worker app.presentation.worker.main:broker`.
Импортирует модули с задачами — TaskIQ авторегистрирует их через `@broker.task`.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.tasks.broker import broker  # noqa: F401 — re-export для taskiq CLI

# Регистрация задач: при импорте этих модулей их `@broker.task`-декораторы
# добавляют таски в broker.tasks.
from app.infrastructure.tasks import outbox_dispatcher  # noqa: F401
from app.infrastructure.tasks import repagination  # noqa: F401

if __name__ == "__main__":  # запуск напрямую как health-контейнер
    # Простой "pong"-режим: держим процесс живым, чтобы compose healthcheck'ов хватило.
    # В проде запускать через `taskiq worker`.
    setup_logging(get_settings())

    async def _idle() -> None:
        while True:
            await asyncio.sleep(60)

    asyncio.run(_idle())
