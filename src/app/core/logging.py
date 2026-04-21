"""structlog + stdlib logging: JSON в prod, console в dev. PII scrubbing."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import LogRenderer, Settings

_PII_KEYS = frozenset(
    {
        "first_name",
        "last_name",
        "full_name",
        "phone",
        "text",
        "caption",
        "password",
        "token",
        "secret",
    }
)


def _scrub_pii(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Удалить поля, которые могут содержать PII, из выводимого лога."""
    for key in list(event_dict.keys()):
        if key.lower() in _PII_KEYS:
            event_dict.pop(key, None)
    return event_dict


def setup_logging(settings: Settings) -> None:
    """Сконфигурировать structlog + перехватить stdlib logging."""
    level = getattr(logging, settings.log_level)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _scrub_pii,
    ]

    if settings.log_renderer == LogRenderer.JSON:
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer(
            serializer=_orjson_dumps
        )
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # stdlib logging → structlog (aiogram/sqlalchemy используют stdlib)
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Подавить шумные либы
    for noisy in ("aiogram.event", "aiogram.dispatcher", "asyncio", "aiohttp.access"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def _orjson_dumps(obj: Any, **_kwargs: Any) -> str:
    """orjson serializer с fallback на str для неизвестных типов."""
    import orjson

    return orjson.dumps(obj, default=str).decode("utf-8")


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Получить логгер. Обычно вызывается как `log = get_logger(__name__)`."""
    return structlog.get_logger(name)
