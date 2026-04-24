"""Хелперы для сценариев locust: сборка синтетических Telegram Update-JSON."""

from __future__ import annotations

import random
import time
from typing import Any


def _fresh_tg_id() -> int:
    """Уникальный «юзер» в рамках теста."""
    return random.randint(1_000_000_000, 9_999_999_999)


def make_update_start(tg_id: int | None = None, text: str = "/start") -> dict[str, Any]:
    uid = tg_id if tg_id is not None else _fresh_tg_id()
    now = int(time.time())
    return {
        "update_id": random.randint(1, 2**31 - 1),
        "message": {
            "message_id": random.randint(1, 2**31 - 1),
            "date": now,
            "from": {
                "id": uid,
                "is_bot": False,
                "first_name": "Load",
                "language_code": "ru",
            },
            "chat": {"id": uid, "type": "private", "first_name": "Load"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(text)}]
            if text.startswith("/")
            else [],
        },
    }


def make_callback(
    data: str,
    *,
    tg_id: int | None = None,
    message_id: int | None = None,
) -> dict[str, Any]:
    uid = tg_id if tg_id is not None else _fresh_tg_id()
    now = int(time.time())
    mid = message_id or random.randint(1, 2**31 - 1)
    return {
        "update_id": random.randint(1, 2**31 - 1),
        "callback_query": {
            "id": str(random.randint(1, 2**63 - 1)),
            "from": {"id": uid, "is_bot": False, "first_name": "Load", "language_code": "ru"},
            "chat_instance": str(random.randint(1, 2**63 - 1)),
            "message": {
                "message_id": mid,
                "date": now,
                "chat": {"id": uid, "type": "private"},
                "text": "…",
            },
            "data": data,
        },
    }
