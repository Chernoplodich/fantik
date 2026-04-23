"""Value-объекты домена трекинга."""

from __future__ import annotations

import re
import secrets
import string
from enum import StrEnum

from app.core.errors import ValidationError


class TrackingEventType(StrEnum):
    START = "start"
    REGISTER = "register"
    FIRST_READ = "first_read"
    FIRST_PUBLISH = "first_publish"
    CUSTOM = "custom"


_BASE62_ALPHABET = string.ascii_letters + string.digits
_CODE_RE = re.compile(r"^[A-Za-z0-9]{6,16}$")


class TrackingCodeStr(str):
    """URL-safe код UTM-источника: 6–16 символов base62."""

    __slots__ = ()

    def __new__(cls, value: str) -> TrackingCodeStr:
        if not isinstance(value, str):
            raise ValidationError("tracking code must be a string")
        if not _CODE_RE.fullmatch(value):
            raise ValidationError("Код должен быть 6–16 символов, только A-Z a-z 0-9.")
        return super().__new__(cls, value)


def generate_code(length: int = 8) -> TrackingCodeStr:
    """Сгенерировать случайный base62-код фиксированной длины."""
    if not 6 <= length <= 16:
        raise ValidationError("Длина кода должна быть 6–16.")
    code = "".join(secrets.choice(_BASE62_ALPHABET) for _ in range(length))
    return TrackingCodeStr(code)
