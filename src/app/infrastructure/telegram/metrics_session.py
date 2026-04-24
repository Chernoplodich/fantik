"""AiohttpSession с замером метрик всех исходящих TG API-вызовов.

Подменяет стандартную сессию aiogram'а. На каждый `make_request`:
- инкрементит `BOT_TG_API_CALLS_TOTAL{method, result}`;
- наблюдает duration в `BOT_TG_API_DURATION{method}`.

При наличии `telegram_api_base_url` — работает через `TelegramAPIServer.from_base(...)`,
что нужно для load-тестов с fake-tg сервером.
"""

from __future__ import annotations

import time
from typing import Any

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.methods import TelegramMethod

from app.core.metrics import BOT_TG_API_CALLS, BOT_TG_API_DURATION


class MetricsAiohttpSession(AiohttpSession):
    """AiohttpSession + Prometheus-метрики. API-совместим со стандартной."""

    async def make_request(
        self,
        bot: Any,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        method_name = method.__class__.__name__
        start = time.monotonic()
        result = "error"
        try:
            value = await super().make_request(bot, method, timeout)
            result = "ok"
            return value
        finally:
            BOT_TG_API_CALLS.labels(method=method_name, result=result).inc()
            BOT_TG_API_DURATION.labels(method=method_name).observe(time.monotonic() - start)


def build_metrics_session(tg_api_base: str | None = None) -> MetricsAiohttpSession:
    """Создать MetricsAiohttpSession, опционально с кастомным API base для load-тестов."""
    if tg_api_base:
        server = TelegramAPIServer.from_base(tg_api_base)
        return MetricsAiohttpSession(api=server)
    return MetricsAiohttpSession()
