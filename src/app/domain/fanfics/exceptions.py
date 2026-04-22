"""Доменные ошибки фиков."""

from __future__ import annotations

from app.core.errors import ConflictError, ValidationError


class WrongStatusError(ConflictError):
    """Операция запрещена в текущем статусе фика/главы."""


class ForbiddenActionError(ConflictError):
    """Действие запрещено бизнес-правилами (например, править чужое)."""


class FanficChapterLimitExceededError(ConflictError):
    """Превышен лимит глав (max_chapters_per_fic)."""


class ChapterCharsLimitExceededError(ValidationError):
    """Превышен лимит UTF-16 units в тексте главы."""


class TooManyDailySubmissionsError(ConflictError):
    """Автор превысил дневной лимит подач на модерацию."""


class TooManyTagsError(ValidationError):
    """Слишком много тегов на фик."""


class EmptyFanficError(ConflictError):
    """Нельзя отправить на модерацию фик без глав."""


class InvalidEntityError(ValidationError):
    """Некорректные MessageEntities (schema, overlap, out-of-bounds, text_mention)."""
