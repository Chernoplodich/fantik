"""Доменные ошибки пользователя."""

from __future__ import annotations

from app.core.errors import ConflictError, ForbiddenError


class AuthorNickAlreadyTakenError(ConflictError):
    """Ник автора уже занят другим пользователем."""


class AuthorNickAlreadySetError(ConflictError):
    """Пользователь уже задал ник; смена требует обращения к модератору."""


class UserBannedError(ForbiddenError):
    """Пользователь забанен, действие запрещено."""
