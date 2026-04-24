"""Entrypoint воркера рассылок (broadcast queue).

`python -m app.presentation.worker.broadcast_main` запускает TaskIQ-воркер на
выделенной очереди `broadcast_broker`. Глобальный token-bucket
«broadcast:global» 25 msg/s (или 1000 при allow_paid_broadcast) удерживает
общий rate-limit.
"""

from __future__ import annotations

import os
import sys

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.sentry import init_sentry

# Регистрация task'ов broadcast'а — импорт активирует @broadcast_broker.task.
from app.infrastructure.tasks import broadcast  # noqa: F401
from app.infrastructure.tasks.broker import broadcast_broker  # noqa: F401
from app.presentation.worker._metrics_bootstrap import start_worker_metrics

init_sentry(get_settings(), component="worker-broadcast")
start_worker_metrics()


def _run() -> None:
    setup_logging(get_settings())
    os.execvp(
        "taskiq",
        [
            "taskiq",
            "worker",
            "app.presentation.worker.broadcast_main:broadcast_broker",
            "app.infrastructure.tasks.broadcast",
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
