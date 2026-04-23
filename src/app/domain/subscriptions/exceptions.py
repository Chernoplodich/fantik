"""Доменные ошибки подписок."""

from __future__ import annotations

from app.core.errors import DomainError


class SelfSubscribeError(DomainError):
    """Попытка подписаться на самого себя."""
