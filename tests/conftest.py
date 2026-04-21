"""Общие фикстуры для тестов."""

from __future__ import annotations

import os
from datetime import UTC, datetime

# Тестовые env-значения применяются ДО импорта app.core.config, чтобы get_settings()
# не взрывался на отсутствующих BOT_TOKEN/MEILI_MASTER_KEY в чистом окружении.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("BOT_TOKEN", "111:TEST_TOKEN_FOR_PYTEST_ONLY_NOT_REAL")
os.environ.setdefault("ADMIN_TG_IDS", "1")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("MEILI_MASTER_KEY", "test-master-key-long-enough-for-meili")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


import pytest  # noqa: E402

from app.core.clock import FrozenClock  # noqa: E402


@pytest.fixture
def frozen_clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC))
