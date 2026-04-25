"""Доменные ошибки заявок на фандом."""

from __future__ import annotations

from app.core.errors import ConflictError


class ProposalAlreadyHandledError(ConflictError):
    """Заявка уже одобрена/отклонена — повторное решение запрещено."""
