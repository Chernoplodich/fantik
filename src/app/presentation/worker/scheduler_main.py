"""Entrypoint scheduler'а TaskIQ.

`python -m app.presentation.worker.scheduler_main` запускает реальный scheduler
через CLI. LabelScheduleSource читает периодические задачи из @broker.task(schedule=[...]).
"""

from __future__ import annotations

import os
import sys

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.tasks.broker import scheduler  # noqa: F401 (re-exported for CLI)

# Регистрация задач с `schedule=[...]` — LabelScheduleSource читает их.
from app.infrastructure.tasks import indexing  # noqa: F401
from app.infrastructure.tasks import outbox_dispatcher  # noqa: F401
from app.infrastructure.tasks import repagination  # noqa: F401


def _run() -> None:
    setup_logging(get_settings())
    os.execvp(
        "taskiq",
        [
            "taskiq",
            "scheduler",
            "app.presentation.worker.scheduler_main:scheduler",
            "--log-level",
            get_settings().log_level,
        ],
    )


if __name__ == "__main__":
    if "--idle" in sys.argv:
        import asyncio

        setup_logging(get_settings())

        async def _idle() -> None:
            while True:
                await asyncio.sleep(60)

        asyncio.run(_idle())
    else:
        _run()
