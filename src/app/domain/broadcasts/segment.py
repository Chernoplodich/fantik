"""Чистая интерпретация segment_spec — без SQL, без IO.

Валидирует структуру dict'а и возвращает нормализованный `SegmentPlan`,
который уже InfraRepository превращает в конкретный SELECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.broadcasts.exceptions import SegmentValidationError
from app.domain.broadcasts.value_objects import (
    SEGMENT_KIND_ACTIVE_SINCE_DAYS,
    SEGMENT_KIND_ALL,
    SEGMENT_KIND_AUTHORS,
    SEGMENT_KIND_RETRY_FAILED,
    SEGMENT_KIND_SUBSCRIBERS_OF,
    SEGMENT_KIND_UTM,
)


@dataclass(frozen=True, kw_only=True)
class SegmentPlan:
    """Нормализованный план сегмента, на который InfraRepository смотрит."""

    kind: str
    # Параметры kind-зависимые — валидируются при конструкции.
    days: int | None = None
    author_id: int | None = None
    utm_code: str | None = None
    parent_broadcast_id: int | None = None


_KNOWN_KINDS = frozenset(
    {
        SEGMENT_KIND_ALL,
        SEGMENT_KIND_ACTIVE_SINCE_DAYS,
        SEGMENT_KIND_AUTHORS,
        SEGMENT_KIND_SUBSCRIBERS_OF,
        SEGMENT_KIND_UTM,
        SEGMENT_KIND_RETRY_FAILED,
    }
)


def interpret_segment(spec: dict[str, Any] | None) -> SegmentPlan:
    """Разобрать и валидировать segment_spec."""
    if not spec or not isinstance(spec, dict):
        raise SegmentValidationError("segment_spec пуст.")
    kind = spec.get("kind")
    if kind not in _KNOWN_KINDS:
        raise SegmentValidationError(f"Неизвестный kind сегмента: {kind!r}.")

    if kind == SEGMENT_KIND_ALL:
        return SegmentPlan(kind=kind)

    if kind == SEGMENT_KIND_ACTIVE_SINCE_DAYS:
        value = spec.get("value")
        if not isinstance(value, int) or value <= 0 or value > 3650:
            raise SegmentValidationError(
                "active_since_days.value должен быть положительным int <= 3650."
            )
        return SegmentPlan(kind=kind, days=int(value))

    if kind == SEGMENT_KIND_AUTHORS:
        return SegmentPlan(kind=kind)

    if kind == SEGMENT_KIND_SUBSCRIBERS_OF:
        author_id = spec.get("author_id")
        if not isinstance(author_id, int) or author_id <= 0:
            raise SegmentValidationError("subscribers_of.author_id должен быть положительным int.")
        return SegmentPlan(kind=kind, author_id=int(author_id))

    if kind == SEGMENT_KIND_UTM:
        code = spec.get("code")
        if not isinstance(code, str) or not code.strip():
            raise SegmentValidationError("utm.code должен быть непустой строкой.")
        return SegmentPlan(kind=kind, utm_code=code.strip())

    if kind == SEGMENT_KIND_RETRY_FAILED:
        parent = spec.get("parent_broadcast_id")
        if not isinstance(parent, int) or parent <= 0:
            raise SegmentValidationError(
                "retry_failed.parent_broadcast_id должен быть положительным int."
            )
        return SegmentPlan(kind=kind, parent_broadcast_id=int(parent))

    raise SegmentValidationError(f"Необработанный kind: {kind!r}.")


def describe_segment(spec: dict[str, Any] | None) -> str:
    """Человеко-читаемое описание сегмента — для UI превью рассылки."""
    try:
        plan = interpret_segment(spec)
    except SegmentValidationError as e:
        return f"(невалидный сегмент: {e})"
    if plan.kind == SEGMENT_KIND_ALL:
        return "Все пользователи"
    if plan.kind == SEGMENT_KIND_ACTIVE_SINCE_DAYS:
        return f"Активные за последние {plan.days} дн."
    if plan.kind == SEGMENT_KIND_AUTHORS:
        return "Авторы"
    if plan.kind == SEGMENT_KIND_SUBSCRIBERS_OF:
        return f"Подписчики автора #{plan.author_id}"
    if plan.kind == SEGMENT_KIND_UTM:
        return f"Пришедшие по UTM «{plan.utm_code}»"
    if plan.kind == SEGMENT_KIND_RETRY_FAILED:
        return f"Повтор: упавшие в рассылке #{plan.parent_broadcast_id}"
    return "(неизвестный сегмент)"
