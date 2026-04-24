"""Поднимает Prometheus HTTP-сервер (/metrics + implicit health) в worker-процессах.

Стратегия: функция `start_worker_metrics()` вызывается на module-level из
entry-point'а воркера (`worker/main.py`, `worker/broadcast_main.py`,
`worker/scheduler_main.py`). Модуль импортируется taskiq-CLI уже ПОСЛЕ
`os.execvp`, в целевом процессе — поэтому `prometheus_client.start_http_server`
(daemon thread) живёт столько же, сколько worker.

Порт берётся из `FANTIK_WORKER_METRICS_PORT`; без env метрик нет — удобно для
тестов и --idle режима.
"""

from __future__ import annotations

import os

from app.core.logging import get_logger

log = get_logger(__name__)

_ENV = "FANTIK_WORKER_METRICS_PORT"


def start_worker_metrics() -> None:
    """Старт prometheus HTTP endpoint в daemon-thread'е (если задан env)."""
    raw = os.environ.get(_ENV)
    if not raw:
        return
    try:
        port = int(raw)
    except ValueError:
        log.warning("worker_metrics_port_invalid", value=raw)
        return
    try:
        from prometheus_client import start_http_server

        start_http_server(port)
        log.info("worker_metrics_started", port=port)
    except OSError as e:
        # Порт занят — не падаем, бот/тесты могут переиспользовать один образ.
        log.warning("worker_metrics_start_failed", port=port, error=str(e))
