"""Доменные ошибки модерации."""

from __future__ import annotations

from app.core.errors import ConflictError, ForbiddenError, ValidationError


class CaseAlreadyLockedError(ConflictError):
    """Задание уже залочено другим модератором."""


class CaseNotLockedByThisModeratorError(ForbiddenError):
    """Модератор пытается решить/снять чужой lock."""


class CaseAlreadyDecidedError(ConflictError):
    """Решение уже принято (decision != NULL). Повтор запрещён."""


class CannotModerateOwnWorkError(ForbiddenError):
    """Модератор не может модерировать свои же работы."""


class CaseBeingReviewedError(ConflictError):
    """Попытка отмены/повторной подачи, когда модератор держит активный lock."""


class ReasonsRequiredForRejectError(ValidationError):
    """При reject обязателен хотя бы один reason_id."""
