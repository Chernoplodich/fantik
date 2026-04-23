"""Value-объекты домена фиков."""

from __future__ import annotations

import re
from enum import StrEnum

from app.core.errors import ValidationError


class FicStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISING = "revising"
    ARCHIVED = "archived"


class MqKind(StrEnum):
    FIC_FIRST_PUBLISH = "fic_first_publish"
    FIC_EDIT = "fic_edit"
    CHAPTER_ADD = "chapter_add"
    CHAPTER_EDIT = "chapter_edit"


class MqDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


TITLE_MIN = 2
TITLE_MAX = 128
SUMMARY_MIN = 1
SUMMARY_MAX = 2000
CHAPTER_TITLE_MIN = 1
CHAPTER_TITLE_MAX = 128
TAG_NAME_MIN = 2
TAG_NAME_MAX = 32
TAG_SLUG_MAX = 32
CHAPTER_NUMBER_MIN = 1
CHAPTER_NUMBER_MAX = 200
MAX_TAGS_PER_FIC = 20
MAX_ENTITIES_PER_TEXT = 1000


class FanficTitle(str):
    """Заголовок фика: 2–128 символов, не пустой после trim."""

    __slots__ = ()

    def __new__(cls, value: str) -> "FanficTitle":
        if not isinstance(value, str):
            raise ValidationError("title must be a string")
        cleaned = " ".join(value.split())
        if not (TITLE_MIN <= len(cleaned) <= TITLE_MAX):
            raise ValidationError(f"Заголовок: {TITLE_MIN}–{TITLE_MAX} символов.")
        return super().__new__(cls, cleaned)


class Summary(str):
    """Аннотация фика: 1–2000 символов."""

    __slots__ = ()

    def __new__(cls, value: str) -> "Summary":
        if not isinstance(value, str):
            raise ValidationError("summary must be a string")
        cleaned = value.strip()
        if not (SUMMARY_MIN <= len(cleaned) <= SUMMARY_MAX):
            raise ValidationError(f"Аннотация: {SUMMARY_MIN}–{SUMMARY_MAX} символов.")
        return super().__new__(cls, cleaned)


class ChapterTitle(str):
    """Название главы: 1–128 символов."""

    __slots__ = ()

    def __new__(cls, value: str) -> "ChapterTitle":
        if not isinstance(value, str):
            raise ValidationError("chapter title must be a string")
        cleaned = " ".join(value.split())
        if not (CHAPTER_TITLE_MIN <= len(cleaned) <= CHAPTER_TITLE_MAX):
            raise ValidationError(
                f"Название главы: {CHAPTER_TITLE_MIN}–{CHAPTER_TITLE_MAX} символов."
            )
        return super().__new__(cls, cleaned)


class ChapterNumber(int):
    """Порядковый номер главы: 1..200."""

    __slots__ = ()

    def __new__(cls, value: int) -> "ChapterNumber":
        iv = int(value)
        if not (CHAPTER_NUMBER_MIN <= iv <= CHAPTER_NUMBER_MAX):
            raise ValidationError(
                f"Номер главы должен быть в диапазоне {CHAPTER_NUMBER_MIN}–{CHAPTER_NUMBER_MAX}."
            )
        return super().__new__(cls, iv)


_TAG_NAME_INNER_RE = re.compile(r"^[^\x00-\x1f]{2,32}$")
_TAG_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class TagName(str):
    """Отображаемое имя тега: 2–32 символа, без управляющих."""

    __slots__ = ()

    def __new__(cls, value: str) -> "TagName":
        if not isinstance(value, str):
            raise ValidationError("tag name must be a string")
        cleaned = " ".join(value.split())
        if not _TAG_NAME_INNER_RE.fullmatch(cleaned):
            raise ValidationError(f"Тег: {TAG_NAME_MIN}–{TAG_NAME_MAX} символов.")
        return super().__new__(cls, cleaned)


class TagSlug(str):
    """Slug тега: [a-z0-9-], без ведущих/хвостовых дефисов, макс 32."""

    __slots__ = ()

    def __new__(cls, value: str) -> "TagSlug":
        if not isinstance(value, str):
            raise ValidationError("tag slug must be a string")
        if not value or len(value) > TAG_SLUG_MAX:
            raise ValidationError("tag slug length must be 1–32")
        if not _TAG_SLUG_RE.fullmatch(value):
            raise ValidationError("tag slug must match [a-z0-9](-[a-z0-9])*")
        return super().__new__(cls, value)


class AgeRatingCode(str):
    """Код возрастного рейтинга (G, PG, PG-13, R, M, ...)."""

    __slots__ = ()

    _RE = re.compile(r"^[A-Z][A-Z0-9\-]{0,7}$")

    def __new__(cls, value: str) -> "AgeRatingCode":
        if not isinstance(value, str):
            raise ValidationError("age_rating code must be a string")
        cleaned = value.strip().upper()
        if not cls._RE.fullmatch(cleaned):
            raise ValidationError(f"Invalid age_rating code: {value!r}")
        return super().__new__(cls, cleaned)
