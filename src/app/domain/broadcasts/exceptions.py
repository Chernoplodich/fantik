"""Доменные ошибки рассылок."""

from __future__ import annotations

from app.core.errors import DomainError


class BroadcastNotFoundError(DomainError):
    """Рассылка не найдена по id."""


class InvalidBroadcastTransitionError(DomainError):
    """Запрошенный переход статуса не разрешён текущим статусом."""


class SegmentValidationError(DomainError):
    """Невалидный segment_spec — неизвестный kind или некорректные параметры."""


class KeyboardValidationError(DomainError):
    """Ошибка разбора/валидации клавиатуры wizard'а."""
