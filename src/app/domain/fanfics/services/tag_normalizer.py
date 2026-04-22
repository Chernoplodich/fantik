"""Нормализация тегов: (name, slug).

- name: отображаемое имя (trim + collapse whitespace, регистр автора сохраняем).
- slug: ASCII `[a-z0-9-]`, транслит кириллицы, макс 32 символа.
"""

from __future__ import annotations

import re

from app.core.errors import ValidationError
from app.domain.fanfics.value_objects import TAG_SLUG_MAX, TagName, TagSlug

_CYRILLIC_MAP: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _to_slug(s: str) -> str:
    out: list[str] = []
    for ch in s.lower():
        if ch in _CYRILLIC_MAP:
            out.append(_CYRILLIC_MAP[ch])
        elif "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
        elif ch.isspace() or ch in "-_/.,":
            out.append("-")
        # прочие (латиница с диакритикой, иероглифы и т.п.) — дропаем
    raw = "".join(out)
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw[:TAG_SLUG_MAX].strip("-")


def normalize(raw: str) -> tuple[TagName, TagSlug]:
    """Вернуть (TagName, TagSlug) или поднять ValidationError.

    Raises:
        ValidationError: если после нормализации получилось пусто / несовместимо
            с ограничениями TagName/TagSlug.
    """
    if not isinstance(raw, str):
        raise ValidationError("tag raw must be a string")
    name = TagName(raw)
    slug = _to_slug(str(name))
    if not slug:
        raise ValidationError(
            "Не удалось построить slug тега. Используй буквы/цифры."
        )
    return name, TagSlug(slug)
