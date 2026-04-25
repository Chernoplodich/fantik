"""TaskIQ middleware: метрики duration/retries + Sentry capture_exception.

Подключается в broker.py через `broker.add_middlewares(...)`.
"""

from __future__ import annotations

import time
from typing import Any

import sentry_sdk
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.logging import get_logger
from app.core.metrics import WORKER_TASK_DURATION, WORKER_TASK_RETRIES

log = get_logger(__name__)


class MetricsTaskMiddleware(TaskiqMiddleware):
    """Замер duration + учёт ретраев."""

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        message.labels["__metrics_start"] = str(time.monotonic())
        retry = int(message.labels.get("X-TASKIQ-RETRY", "0") or "0")
        if retry > 0:
            WORKER_TASK_RETRIES.labels(task=message.task_name).inc()
        return message

    async def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:
        raw = message.labels.get("__metrics_start")
        if raw is None:
            return
        try:
            start = float(raw)
        except ValueError:
            return
        elapsed = time.monotonic() - start
        status = "error" if result.is_err else "ok"
        WORKER_TASK_DURATION.labels(task=message.task_name, result=status).observe(elapsed)


class SentryTaskMiddleware(TaskiqMiddleware):
    """Отправляем необработанные ошибки задач в Sentry с тегом task_name."""

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("taskiq.task", message.task_name)
            scope.set_context(
                "taskiq",
                {
                    "task_id": message.task_id,
                    "task_name": message.task_name,
                    "retry": message.labels.get("X-TASKIQ-RETRY", "0"),
                },
            )
            sentry_sdk.capture_exception(exception)
        log.error(
            "taskiq_task_failed",
            task=message.task_name,
            task_id=message.task_id,
            error=type(exception).__name__,
        )
