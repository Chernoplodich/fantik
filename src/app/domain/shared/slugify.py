"""Мини-транслитератор для генерации URL-safe slug'ов.

Покрывает русскую кириллицу + упрощённый fallback: любой неLATIN/цифра →
дефис. Без зависимостей (python-slugify специально не тянем — одной функции
хватит для наших нужд: slug фандома).
"""

from __future__ import annotations

import re

_CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


_NON_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify(value: str, *, max_len: int = 128) -> str:
    """Превратить произвольную строку в slug: латиница+цифры+дефисы.

    - кириллица транслитерируется;
    - остальное (пробелы, знаки, non-latin) схлопывается в «-»;
    - множественные дефисы склеиваются, крайние убираются;
    - результат приводится к нижнему регистру;
    - обрезка до max_len.
    """
    out: list[str] = []
    for ch in value.lower():
        if ch in _CYRILLIC_MAP:
            out.append(_CYRILLIC_MAP[ch])
        else:
            out.append(ch)
    s = "".join(out)
    s = _NON_SLUG_RE.sub("-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if not s:
        return ""
    return s[:max_len].rstrip("-")
