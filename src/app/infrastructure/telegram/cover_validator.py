"""Валидация загружаемой обложки (docs/12 §«Валидация обложек»).

- Только JPEG / PNG — по magic bytes, не по Telegram `mime_type`.
- Размер ≤ `settings.cover_max_size_bytes` (5 МБ по умолчанию).

Telegram после compression не всегда честно пишет mime в PhotoSize, поэтому
мы качаем первые байты через `bot.download` (aiogram сам стримит в BytesIO)
и проверяем сигнатуры.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from io import BytesIO

from aiogram import Bot

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class CoverError(str, Enum):
    TOO_LARGE = "too_large"
    BAD_FORMAT = "bad_format"
    DOWNLOAD_FAILED = "download_failed"


@dataclass(frozen=True)
class CoverValidationResult:
    ok: bool
    format: str | None = None  # "jpeg" / "png" при ok=True
    error: CoverError | None = None  # при ok=False
    size: int | None = None  # сколько байт реально скачали


def _detect_format(data: bytes) -> str | None:
    if data.startswith(_JPEG_MAGIC):
        return "jpeg"
    if data.startswith(_PNG_MAGIC):
        return "png"
    return None


async def validate_cover(
    bot: Bot,
    file_id: str,
    *,
    max_size_bytes: int,
) -> CoverValidationResult:
    """Скачать обложку в память, проверить размер и magic bytes."""
    try:
        file = await bot.get_file(file_id)
    except Exception:
        return CoverValidationResult(ok=False, error=CoverError.DOWNLOAD_FAILED)

    reported = getattr(file, "file_size", None)
    if reported is not None and int(reported) > int(max_size_bytes):
        return CoverValidationResult(ok=False, error=CoverError.TOO_LARGE, size=int(reported))

    buf = BytesIO()
    try:
        await bot.download(file, destination=buf)
    except Exception:
        return CoverValidationResult(ok=False, error=CoverError.DOWNLOAD_FAILED)

    data = buf.getvalue()
    size = len(data)
    if size > int(max_size_bytes):
        return CoverValidationResult(ok=False, error=CoverError.TOO_LARGE, size=size)

    fmt = _detect_format(data[:16])
    if fmt is None:
        return CoverValidationResult(ok=False, error=CoverError.BAD_FORMAT, size=size)
    return CoverValidationResult(ok=True, format=fmt, size=size)
