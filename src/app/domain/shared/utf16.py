"""Утилиты UTF-16: длина строки в code units.

Telegram MessageEntity.offset/length — UTF-16 code units. Python string
индексируется по code points. Для валидации лимитов глав и корректности
offset/length нужно считать длину в UTF-16.
"""

from __future__ import annotations


def utf16_length(s: str) -> int:
    """Длина строки в UTF-16 code units.

    Суррогатная пара (эмодзи вне BMP) = 2 units.
    """
    return len(s.encode("utf-16-le")) // 2


def utf16_units_of_char(ch: str) -> int:
    """Сколько UTF-16 кодовых единиц занимает один code point."""
    return 2 if ord(ch) > 0xFFFF else 1
