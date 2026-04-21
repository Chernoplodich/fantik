"""Абстракция времени: в тестах подменяется на FrozenClock."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Обычные системные UTC-часы."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class FrozenClock:
    """Для тестов: возвращает заданное время."""

    def __init__(self, at: datetime) -> None:
        self._at = at

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = at
