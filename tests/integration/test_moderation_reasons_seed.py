"""Integration test: 7 причин отказа засиданы миграцией 0003."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestReasonsSeed:
    async def test_seven_reasons_present(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.connect() as conn:
                res = await conn.execute(
                    text("SELECT count(*) FROM moderation_reasons WHERE active")
                )
                assert res.scalar_one() == 7
                codes = [
                    r[0]
                    for r in (
                        await conn.execute(
                            text("SELECT code FROM moderation_reasons ORDER BY sort_order")
                        )
                    ).all()
                ]
                assert codes == [
                    "RATING_MISMATCH",
                    "PLAGIARISM",
                    "LOW_QUALITY",
                    "NO_FANDOM",
                    "INVALID_FORMAT",
                    "WRONG_TAGS",
                    "RULES_VIOLATION",
                ]
        finally:
            await engine.dispose()
