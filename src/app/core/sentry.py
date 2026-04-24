"""Инициализация Sentry SDK для всех entry-points с PII-scrubbing.

Политика (docs/12 §177–180):
- `send_default_pii=False` — Sentry не вытаскивает PII из фреймворков.
- `before_send` дополнительно рубит: `text`, `caption`, `first_name`, `last_name`,
  `full_name`, `phone`, `password`, `token`, `secret` из breadcrumbs/extras/contexts.
- `event.user` ужимаем до `{id: tg_id}`.

Если `settings.sentry_dsn` пуст — init no-op.
"""

from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.core.config import Settings

_PII_KEYS = frozenset(
    {
        "text",
        "caption",
        "first_name",
        "last_name",
        "full_name",
        "phone",
        "password",
        "token",
        "secret",
    }
)


def _strip_keys(obj: Any, keys: frozenset[str]) -> None:
    """Рекурсивно вырезать `keys` из dict/list — безопасно для None/скаляров."""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if k.lower() in keys:
                obj.pop(k, None)
            else:
                _strip_keys(obj[k], keys)
    elif isinstance(obj, list):
        for item in obj:
            _strip_keys(item, keys)


def scrub_pii_event(
    event: dict[str, Any], _hint: dict[str, Any] | None
) -> dict[str, Any] | None:
    """before_send/before_send_transaction hook.

    Ужимаем `user` до `id`, режем PII-ключи в breadcrumbs/extras/contexts/request.
    """
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user.get("id")} if "id" in user else {}

    for section in ("extra", "contexts", "request", "tags"):
        if section in event:
            _strip_keys(event[section], _PII_KEYS)

    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        values = breadcrumbs.get("values")
        if isinstance(values, list):
            for bc in values:
                if isinstance(bc, dict):
                    _strip_keys(bc.get("data", {}), _PII_KEYS)
                    # message в breadcrumb может содержать сырой текст — срезаем до уровня
                    if "message" in bc and bc.get("category") in {"telegram.update", "telegram.message"}:
                        bc["message"] = "<scrubbed>"

    return event


def init_sentry(settings: Settings, *, component: str) -> bool:
    """Инициализировать Sentry для текущего процесса.

    Args:
        settings: глобальные настройки.
        component: тег процесса (`bot`, `worker`, `worker-broadcast`, `scheduler`).

    Returns:
        True — если Sentry реально поднят; False — если DSN пуст и инит пропущен.
    """
    if not settings.sentry_dsn:
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env.value,
        release=settings.release or None,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        attach_stacktrace=False,
        integrations=[
            AsyncioIntegration(),
            SqlalchemyIntegration(),
            RedisIntegration(),
            AioHttpIntegration(),
        ],
        before_send=scrub_pii_event,
        before_send_transaction=scrub_pii_event,
    )
    sentry_sdk.set_tag("component", component)
    return True
