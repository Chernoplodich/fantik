"""Тесты валидатора обложек: magic bytes (JPEG/PNG) и лимит размера."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.telegram.cover_validator import (
    CoverError,
    validate_cover,
)

JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
GARBAGE = b"<svg>not an image</svg>"


def _bot_with_download(data: bytes, *, reported_size: int | None = None) -> Any:
    file_mock = MagicMock()
    file_mock.file_size = reported_size

    async def _download(_file: object, destination: BytesIO) -> None:
        destination.write(data)

    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=file_mock)
    bot.download = AsyncMock(side_effect=_download)
    return bot


@pytest.mark.asyncio
async def test_validate_jpeg_ok() -> None:
    bot = _bot_with_download(JPEG_HEADER + b"\x00" * 100)
    res = await validate_cover(bot, "fid", max_size_bytes=5 * 1024 * 1024)
    assert res.ok
    assert res.format == "jpeg"


@pytest.mark.asyncio
async def test_validate_png_ok() -> None:
    bot = _bot_with_download(PNG_HEADER + b"\x00" * 100)
    res = await validate_cover(bot, "fid", max_size_bytes=5 * 1024 * 1024)
    assert res.ok
    assert res.format == "png"


@pytest.mark.asyncio
async def test_validate_bad_format() -> None:
    bot = _bot_with_download(GARBAGE)
    res = await validate_cover(bot, "fid", max_size_bytes=5 * 1024 * 1024)
    assert not res.ok
    assert res.error is CoverError.BAD_FORMAT


@pytest.mark.asyncio
async def test_validate_too_large_by_reported_size() -> None:
    bot = _bot_with_download(JPEG_HEADER + b"\x00", reported_size=10 * 1024 * 1024)
    res = await validate_cover(bot, "fid", max_size_bytes=5 * 1024 * 1024)
    assert not res.ok
    assert res.error is CoverError.TOO_LARGE


@pytest.mark.asyncio
async def test_validate_too_large_by_actual_bytes() -> None:
    # Telegram соврал про file_size (или None), а по факту скачали больше.
    payload = JPEG_HEADER + b"\x00" * (6 * 1024 * 1024)
    bot = _bot_with_download(payload, reported_size=None)
    res = await validate_cover(bot, "fid", max_size_bytes=5 * 1024 * 1024)
    assert not res.ok
    assert res.error is CoverError.TOO_LARGE


@pytest.mark.asyncio
async def test_validate_download_error() -> None:
    bot = MagicMock()
    bot.get_file = AsyncMock(side_effect=RuntimeError("network"))
    res = await validate_cover(bot, "fid", max_size_bytes=5 * 1024 * 1024)
    assert not res.ok
    assert res.error is CoverError.DOWNLOAD_FAILED
