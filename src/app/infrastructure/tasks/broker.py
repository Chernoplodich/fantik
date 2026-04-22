"""TaskIQ broker + scheduler: конфигурация и регистрация задач.

У нас две очереди:
- default (app.presentation.worker.main) — индексация, уведомления, репагинация, outbox.
- broadcast (app.presentation.worker.broadcast_main) — доставка рассылок с rate-limit'ом.
"""

from __future__ import annotations

from taskiq import AsyncBroker, InMemoryBroker, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend, RedisScheduleSource

from app.core.config import AppEnv, Settings, get_settings


def _make_broker(settings: Settings, queue_name: str) -> AsyncBroker:
    if settings.app_env == AppEnv.TEST:
        return InMemoryBroker()
    redis_url = settings.redis_url_for(settings.redis_taskiq_db)
    return ListQueueBroker(
        url=redis_url,
        queue_name=queue_name,
    ).with_result_backend(RedisAsyncResultBackend(redis_url=redis_url, result_ex_time=3600))


settings = get_settings()

# default queue — общие задачи
broker: AsyncBroker = _make_broker(settings, settings.taskiq_queue_default)

# broadcast queue — выделенный пул воркеров с rate-limit'ом
broadcast_broker: AsyncBroker = _make_broker(settings, settings.taskiq_queue_broadcast)

# Scheduler живёт на том же Redis:
#  - LabelScheduleSource читает периодические задачи из @broker.task(schedule=[...]).
#  - RedisScheduleSource — для динамических расписаний (добавляются в рантайме).
scheduler: TaskiqScheduler = TaskiqScheduler(
    broker=broker,
    sources=(
        [
            LabelScheduleSource(broker),
            RedisScheduleSource(settings.redis_url_for(settings.redis_taskiq_db)),
        ]
        if settings.app_env != AppEnv.TEST
        else [LabelScheduleSource(broker)]
    ),
)
