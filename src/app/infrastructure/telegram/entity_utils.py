"""Утилиты работы с Telegram MessageEntity.

ГЛАВНАЯ МЫСЛЬ: `offset` и `length` в MessageEntity — в UTF-16 code units,
а Python-строка индексируется по code points. Для каждого code point
нужно знать, 1 или 2 UTF-16 units он занимает (суррогатные пары для emoji).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


def utf16_length(s: str) -> int:
    """Длина строки в UTF-16 code units."""
    # encode в UTF-16-LE без BOM: 2 байта на unit, длина байтов // 2 = кол-во units
    return len(s.encode("utf-16-le")) // 2


def utf16_units_of_char(ch: str) -> int:
    """1 или 2 — сколько UTF-16 кодовых единиц занимает символ."""
    return 2 if ord(ch) > 0xFFFF else 1


def char_to_utf16(s: str, idx: int) -> int:
    """Перевести позицию в code points → в UTF-16 units."""
    if idx <= 0:
        return 0
    if idx >= len(s):
        return utf16_length(s)
    return utf16_length(s[:idx])


def utf16_to_char(s: str, u: int) -> int:
    """Обратная операция: позиция в UTF-16 units → позиция в code points.

    Если `u` попадает внутрь суррогатной пары — округляем вниз (начало пары).
    """
    if u <= 0:
        return 0
    units = 0
    for i, ch in enumerate(s):
        next_units = units + utf16_units_of_char(ch)
        if next_units > u:
            return i
        units = next_units
        if units == u:
            return i + 1
    return len(s)


@dataclass(frozen=True)
class EntityDict:
    """Удобная обёртка над MessageEntity-словарём Telegram API."""

    type: str
    offset: int
    length: int
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "offset": self.offset, "length": self.length, **self.extra}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EntityDict":
        extra = {k: v for k, v in d.items() if k not in {"type", "offset", "length"}}
        return cls(type=d["type"], offset=int(d["offset"]), length=int(d["length"]), extra=extra)


def normalize_entities(entities: Iterable[dict[str, Any]] | None) -> list[EntityDict]:
    """Нормализовать список entities к списку EntityDict, отфильтровав None и повреждённые."""
    if not entities:
        return []
    out: list[EntityDict] = []
    for e in entities:
        try:
            out.append(EntityDict.from_dict(e))
        except (KeyError, TypeError, ValueError):
            continue  # мусор молча выкидываем
    return sorted(out, key=lambda x: (x.offset, -x.length))


def entities_to_api(entities: list[EntityDict]) -> list[dict[str, Any]]:
    """Обратная конверсия — для send_message(entities=...)."""
    return [e.to_dict() for e in entities]
