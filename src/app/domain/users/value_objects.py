"""Value-объекты домена пользователей."""

from __future__ import annotations

import re
from enum import StrEnum

from app.core.errors import ValidationError


class Role(StrEnum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


_NICK_RE = re.compile(r"^[a-zA-Z0-9_-]{2,32}$")


class AuthorNick(str):
    """Ник автора. Иммутабельный wrapping над str с валидацией.

    Правила:
      - 2–32 символа
      - [A-Za-z0-9_-]
      - UNIQUE игнорируя регистр (проверяется на уровне БД по LOWER(nick))
    """

    __slots__ = ()

    def __new__(cls, value: str) -> "AuthorNick":
        if not isinstance(value, str):
            raise ValidationError("author_nick must be a string")
        cleaned = value.strip()
        if not _NICK_RE.fullmatch(cleaned):
            raise ValidationError("Ник 2–32 символа, только латиница, цифры, _ и -.")
        return super().__new__(cls, cleaned)

    @property
    def lowered(self) -> str:
        return self.lower()
