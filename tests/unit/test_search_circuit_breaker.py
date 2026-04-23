"""Unit: circuit-breaker logic у MeiliSearchIndex.

Тестируем только логику открытия/закрытия — без реальных Meili-вызовов.
Вместо AsyncClient — минимальная заглушка.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.search.indexer import MeiliSearchIndex


def _make_client_with_failing_op() -> MagicMock:
    """Фейковый AsyncClient с падающим index().delete_document()."""
    client = MagicMock()
    index = MagicMock()
    index.delete_document = AsyncMock(side_effect=RuntimeError("down"))
    index.add_documents = AsyncMock(side_effect=RuntimeError("down"))
    client.index.return_value = index
    return client


@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_is_open_initially_false(self) -> None:
        idx = MeiliSearchIndex(_make_client_with_failing_op())
        assert idx.is_open() is False

    async def test_opens_after_three_consecutive_failures(self) -> None:
        idx = MeiliSearchIndex(_make_client_with_failing_op())
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await idx.delete(1)
        assert idx.is_open() is True

    async def test_two_failures_dont_open(self) -> None:
        idx = MeiliSearchIndex(_make_client_with_failing_op())
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await idx.delete(1)
        assert idx.is_open() is False

    async def test_success_resets_counter(self) -> None:
        client = _make_client_with_failing_op()
        idx = MeiliSearchIndex(client)
        # 2 fails
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await idx.delete(1)
        # теперь делаем операцию успешной и добиваем успех
        client.index.return_value.delete_document = AsyncMock(return_value=None)
        await idx.delete(1)
        # счётчик обнулён — ещё 2 ошибки не должны открыть контур
        client.index.return_value.delete_document = AsyncMock(side_effect=RuntimeError("down"))
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await idx.delete(1)
        assert idx.is_open() is False

    async def test_open_timer_expires_into_half_open(self) -> None:
        idx = MeiliSearchIndex(_make_client_with_failing_op())
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await idx.delete(1)
        assert idx.is_open() is True
        # искусственно сдвигаем timer в прошлое — имитация истечения 60+jitter секунд
        idx._open_until = datetime.now(tz=UTC) - timedelta(seconds=1)
        # первый is_open() после истечения должен сбросить контур (half-open)
        assert idx.is_open() is False

    async def test_jitter_in_open_until(self) -> None:
        """Timer должен быть в окне [60-10, 60+10] секунд от now."""
        idx = MeiliSearchIndex(_make_client_with_failing_op())
        start = datetime.now(tz=UTC)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await idx.delete(1)
        assert idx._open_until is not None
        delta = (idx._open_until - start).total_seconds()
        assert 49.9 <= delta <= 70.1
