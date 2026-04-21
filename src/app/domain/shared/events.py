"""Базовый класс доменного события + буфер для агрегатов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """Иммутабельное доменное событие."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    # Имя события для сериализации. Переопределяется наследниками при необходимости.
    name: ClassVar[str] = "domain.event"


class EventEmitter:
    """Мешок событий внутри агрегата. UoW вычитывает их перед commit'ом."""

    __slots__ = ("_events",)

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    def _emit(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        out, self._events = self._events, []
        return out
