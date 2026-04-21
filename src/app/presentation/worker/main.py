"""Entrypoint обычного TaskIQ-воркера (default queue).

Запускается через `taskiq worker app.presentation.worker.main:broker`.
Этот модуль ничего больше не делает, кроме импорта и регистрации задач.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.tasks.broker import broker  # noqa: F401 — re-export для taskiq CLI

# Здесь будут подключаться задачи по мере появления в Этапе 2+.
# Пока модуль пустой — воркер просто готов принимать задачи.

if __name__ == "__main__":  # запуск напрямую как health-контейнер
    # Простой "pong"-режим: держим процесс живым, чтобы compose healthcheck'ов хватило,
    # когда задач ещё нет. В проде запускать через `taskiq worker`.
    setup_logging(get_settings())

    async def _idle() -> None:
        while True:
            await asyncio.sleep(60)

    asyncio.run(_idle())
