"""Иерархия ошибок. Доменные отдельно, прикладные отдельно, инфраструктурные отдельно."""

from __future__ import annotations


class AppError(Exception):
    """Базовая ошибка приложения."""


# ---------- Domain ----------


class DomainError(AppError):
    """Нарушение бизнес-правил. Разрешается к отображению пользователю (аккуратно)."""


class ValidationError(DomainError):
    """Невалидные входные данные с точки зрения доменной модели."""


class NotFoundError(DomainError):
    """Сущность не найдена."""


class ConflictError(DomainError):
    """Конфликт состояния (например, ник занят, статус не позволяет действие)."""


class ForbiddenError(DomainError):
    """Недостаточно прав."""


# ---------- Application ----------


class ApplicationError(AppError):
    """Ошибка прикладного слоя, не связанная с бизнес-правилами напрямую."""


# ---------- Infrastructure ----------


class InfrastructureError(AppError):
    """Ошибка во внешних зависимостях (БД, Redis, Meili, TG API)."""


class SearchUnavailableError(InfrastructureError):
    """Поисковый движок недоступен."""


class CacheUnavailableError(InfrastructureError):
    """Redis недоступен."""
