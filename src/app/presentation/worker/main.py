"""Entrypoint обычного TaskIQ-воркера (default queue).

`python -m app.presentation.worker.main` запускает реальный TaskIQ-воркер
через CLI (execvp) — так он подхватывает задачи из очереди. Сам модуль
импортирует файлы с `@broker.task`, чтобы discovery увидел их.
"""

from __future__ import annotations

import os
import sys

from app.core.config import get_settings
from app.core.logging import setup_logging

# Регистрация задач: при импорте этих модулей их `@broker.task`-декораторы
# добавляют таски в broker.tasks.
from app.infrastructure.tasks import (
    broadcast_scheduler,  # noqa: F401
    indexing,  # noqa: F401
    notifications,  # noqa: F401
    outbox_dispatcher,  # noqa: F401
    repagination,  # noqa: F401
)
from app.infrastructure.tasks.broker import broker  # noqa: F401 (re-exported for CLI)


def _run() -> None:
    setup_logging(get_settings())
    # execvp заменяет текущий процесс — `tini` остаётся PID 1, taskiq становится
    # его потомком и корректно принимает SIGTERM при compose down/restart.
    os.execvp(
        "taskiq",
        [
            "taskiq",
            "worker",
            "app.presentation.worker.main:broker",
            # Явный список модулей с задачами — без `--fs-discover`, который пытается
            # сканировать .venv и падает на произвольных модулях.
            "app.infrastructure.tasks.repagination",
            "app.infrastructure.tasks.indexing",
            "app.infrastructure.tasks.notifications",
            "app.infrastructure.tasks.outbox_dispatcher",
            "app.infrastructure.tasks.broadcast_scheduler",
            "--log-level",
            get_settings().log_level,
        ],
    )


if __name__ == "__main__":
    # `python -m ... --idle` — резервный режим (health-заглушка), если нужно поднять
    # контейнер без запуска воркера (например для дебага).
    if "--idle" in sys.argv:
        import asyncio

        setup_logging(get_settings())

        async def _idle() -> None:
            while True:
                await asyncio.sleep(60)

        asyncio.run(_idle())
    else:
        _run()
