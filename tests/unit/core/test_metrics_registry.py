"""Метрики регистрируются без конфликта имён и имеют валидные labels."""

from __future__ import annotations

from prometheus_client import REGISTRY

from app.core import metrics  # noqa: F401 — сам импорт регистрирует метрики


def _names() -> set[str]:
    names: set[str] = set()
    for col in REGISTRY._collector_to_names.values():  # type: ignore[attr-defined]
        names.update(col)
    return names


def test_bot_metrics_present() -> None:
    names = _names()
    for n in (
        "bot_updates_total",
        "bot_handler_duration_seconds",
        "bot_handler_errors_total",
        "bot_tg_api_calls_total",
        "bot_tg_api_duration_seconds",
        "bot_rate_limit_hits_total",
    ):
        assert n in names


def test_worker_metrics_present() -> None:
    names = _names()
    for n in (
        "worker_task_duration_seconds",
        "worker_task_retries_total",
        "worker_queue_depth",
    ):
        assert n in names


def test_broadcast_metrics_present() -> None:
    names = _names()
    assert "broadcast_deliveries_total" in names
    assert "broadcast_bucket_wait_seconds" in names


def test_domain_metrics_present() -> None:
    names = _names()
    for n in (
        "moderation_queue_depth",
        "moderation_decisions_total",
        "moderation_decision_latency_seconds",
        "fanfics_published_total",
        "chapters_published_total",
        "search_queries_total",
        "search_cache_hits_total",
        "search_cache_misses_total",
        "users_total",
        "active_users_24h",
        "outbox_oldest_pending_age_seconds",
    ):
        assert n in names


def test_metrics_mutation_does_not_raise() -> None:
    # Smoke: лейблы совпадают с сигнатурой.
    metrics.BOT_UPDATES_TOTAL.labels(type="message").inc()
    metrics.BOT_HANDLER_LATENCY.labels(handler="h", result="ok").observe(0.01)
    metrics.BROADCAST_DELIVERIES.labels(status="sent").inc()
    metrics.MODERATION_DECISIONS.labels(decision="approve").inc()
    metrics.SEARCH_QUERIES.labels(backend="meili").inc()
