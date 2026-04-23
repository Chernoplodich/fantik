"""Утилиты работы с Telegram MessageEntity.

ГЛАВНАЯ МЫСЛЬ: `offset` и `length` в MessageEntity — в UTF-16 code units,
а Python-строка индексируется по code points. Для каждого code point
нужно знать, 1 или 2 UTF-16 units он занимает (суррогатные пары для emoji).

UTF-16-конверторы живут в доменном слое (`app.domain.shared.utf16`) —
здесь они ре-экспортированы для совместимости с кодом Этапа 1 и тестами.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.domain.shared.utf16 import (
    char_to_utf16 as char_to_utf16,
)
from app.domain.shared.utf16 import (
    utf16_length as utf16_length,
)
from app.domain.shared.utf16 import (
    utf16_to_char as utf16_to_char,
)
from app.domain.shared.utf16 import (
    utf16_units_of_char as utf16_units_of_char,
)

__all__ = [
    "EntityDict",
    "char_to_utf16",
    "entities_to_api",
    "normalize_entities",
    "utf16_length",
    "utf16_to_char",
    "utf16_units_of_char",
]


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
    def from_dict(cls, d: dict[str, Any]) -> EntityDict:
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
