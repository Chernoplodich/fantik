"""Тесты конфигурации: парсинг admin_tg_ids, построение URL-ов."""

from __future__ import annotations

import os

import pytest

from app.core.config import Settings


def _mk(**overrides: str) -> Settings:
    base = {
        "BOT_TOKEN": "111:FAKE_TOKEN_FOR_TESTS_THAT_IS_LONG_ENOUGH",
        "POSTGRES_PASSWORD": "pw",
        "MEILI_MASTER_KEY": "meili-master-key-long-enough-for-tests",
        "ADMIN_TG_IDS": "",
    }
    base.update(overrides)
    old = {}
    for k, v in base.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        return Settings()  # type: ignore[call-arg]
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestAdminTgIds:
    def test_empty(self) -> None:
        s = _mk(ADMIN_TG_IDS="")
        assert s.admin_tg_ids == []

    def test_single(self) -> None:
        s = _mk(ADMIN_TG_IDS="777")
        assert s.admin_tg_ids == [777]

    def test_multiple_with_spaces(self) -> None:
        s = _mk(ADMIN_TG_IDS="1, 2, 3 , 4")
        assert s.admin_tg_ids == [1, 2, 3, 4]

    def test_invalid_int_raises(self) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011 — pydantic validation
            _mk(ADMIN_TG_IDS="1,abc")


class TestPostgresUrl:
    def test_built_from_parts(self) -> None:
        s = _mk(POSTGRES_USER="u", POSTGRES_PASSWORD="pw", POSTGRES_HOST="h", POSTGRES_PORT="5433")
        assert s.postgres_url == "postgresql+asyncpg://u:pw@h:5433/fantik"

    def test_explicit_dsn_overrides(self) -> None:
        s = _mk(POSTGRES_DSN="postgresql+asyncpg://x:y@z:5432/db")
        assert s.postgres_url == "postgresql+asyncpg://x:y@z:5432/db"


class TestRedisUrlFor:
    def test_with_db(self) -> None:
        s = _mk(REDIS_URL="redis://redis:6379/0")
        assert s.redis_url_for(2) == "redis://redis:6379/2"

    def test_with_db_no_trailing(self) -> None:
        s = _mk(REDIS_URL="redis://redis:6379")
        assert s.redis_url_for(3) == "redis://redis:6379/3"
