"""Доменные ошибки жалоб."""

from __future__ import annotations

from app.core.errors import ConflictError, DomainError


class SelfReportError(DomainError):
    """Попытка пожаловаться на свою же работу."""


class ReportAlreadyHandledError(ConflictError):
    """Жалоба уже обработана (dismissed/actioned) — повторное решение запрещено."""
