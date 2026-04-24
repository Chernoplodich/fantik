"""Централизованные Prometheus-метрики по докам docs/14-observability.md.

Единственное место определения. Импортировать только отсюда — иначе двойная
регистрация в `REGISTRY` даст `Duplicated timeseries`.

Модули-потребители делают:

    from app.core.metrics import BOT_UPDATES_TOTAL
    BOT_UPDATES_TOTAL.labels(type="message").inc()

Label cardinality — сознательно низкая (type: message/callback/inline; result:
ok/error; decision: approve/reject/...), иначе Prometheus задыхается.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# Bot (presentation)
# ============================================================================

BOT_UPDATES_TOTAL = Counter(
    "bot_updates_total",
    "Received Telegram updates by type.",
    ["type"],  # message / callback_query / inline_query / chat_member / my_chat_member / other
)

BOT_HANDLER_LATENCY = Histogram(
    "bot_handler_duration_seconds",
    "Bot handler execution latency.",
    ["handler", "result"],  # handler=qualified name; result=ok/error
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

BOT_HANDLER_ERRORS = Counter(
    "bot_handler_errors_total",
    "Bot handler exceptions.",
    ["handler", "error_type"],
)

BOT_TG_API_CALLS = Counter(
    "bot_tg_api_calls_total",
    "Outgoing Telegram Bot API calls.",
    ["method", "result"],  # result=ok/error
)

BOT_TG_API_DURATION = Histogram(
    "bot_tg_api_duration_seconds",
    "Outgoing Telegram Bot API latency.",
    ["method"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

BOT_RATE_LIMIT_HITS = Counter(
    "bot_rate_limit_hits_total",
    "Anti-flood / throttle rejections.",
    ["scope"],  # user / global
)


# ============================================================================
# Worker (TaskIQ)
# ============================================================================

WORKER_TASK_DURATION = Histogram(
    "worker_task_duration_seconds",
    "TaskIQ task duration.",
    ["task", "result"],  # result=ok/error
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

WORKER_TASK_RETRIES = Counter(
    "worker_task_retries_total",
    "TaskIQ retry attempts.",
    ["task"],
)

WORKER_QUEUE_DEPTH = Gauge(
    "worker_queue_depth",
    "Pending messages in a queue (scraped periodically).",
    ["queue"],
)


# ============================================================================
# Broadcast
# ============================================================================

BROADCAST_DELIVERIES = Counter(
    "broadcast_deliveries_total",
    "Broadcast delivery attempts.",
    ["status"],  # sent / failed / blocked
)

BROADCAST_BUCKET_WAIT = Histogram(
    "broadcast_bucket_wait_seconds",
    "Time waited for global broadcast token bucket.",
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


# ============================================================================
# Domain: moderation, publication, search
# ============================================================================

MODERATION_QUEUE_DEPTH = Gauge(
    "moderation_queue_depth",
    "Open moderation cases by kind (scraped periodically).",
    ["kind"],  # new_fic / edited_fic / new_chapter / report
)

MODERATION_DECISIONS = Counter(
    "moderation_decisions_total",
    "Moderation decisions.",
    ["decision"],  # approve / reject / revise
)

MODERATION_DECISION_LATENCY = Histogram(
    "moderation_decision_latency_seconds",
    "Time from submission to moderator decision.",
    buckets=(60.0, 300.0, 900.0, 1800.0, 3600.0, 10800.0, 21600.0, 43200.0, 86400.0),
)

FIC_PUBLISHED_TOTAL = Counter(
    "fanfics_published_total",
    "First-publish events of fanfics.",
)

CHAPTER_PUBLISHED_TOTAL = Counter(
    "chapters_published_total",
    "Approved chapter-add events (new chapters on already-published fics).",
)

SEARCH_QUERIES = Counter(
    "search_queries_total",
    "Executed search queries.",
    ["backend"],  # meili / pg
)

SEARCH_CACHE_HITS = Counter(
    "search_cache_hits_total",
    "Search cache hits.",
)

SEARCH_CACHE_MISSES = Counter(
    "search_cache_misses_total",
    "Search cache misses.",
)


# ============================================================================
# Business gauges (обновляются metrics_refresh_tick раз в минуту)
# ============================================================================

USERS_TOTAL = Gauge("users_total", "Total registered users.")
ACTIVE_USERS_24H = Gauge("active_users_24h", "Users seen in last 24h.")
FICS_APPROVED_TOTAL_G = Gauge("fics_approved_total", "Currently approved fanfics.")

# Возраст самого старого неопубликованного outbox-события, сек. Дроп в 0 — хорошо.
OUTBOX_OLDEST_PENDING_AGE = Gauge(
    "outbox_oldest_pending_age_seconds",
    "Age of the oldest outbox record with published_at IS NULL.",
)
