"""Утилиты UTF-16: длина строки и позиционные переводы.

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


def char_to_utf16(s: str, idx: int) -> int:
    """Перевести позицию в code points → в UTF-16 units."""
    if idx <= 0:
        return 0
    if idx >= len(s):
        return utf16_length(s)
    return utf16_length(s[:idx])


def utf16_to_char(s: str, u: int) -> int:
    """Обратная операция: UTF-16 units → code points.

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
