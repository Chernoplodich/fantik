"""Единая таблица категорий фандомов и связанных текстов/эмодзи.

Используется одновременно из:
- мастера создания фика (выбор фандома, предложение нового),
- фильтров поиска (двухступенчатый пикер),
- админ-панели CRUD фандомов.

Порядок и набор должны соответствовать docs (см. docs/03-data-model.md
и плану `vivid-moseying-biscuit.md`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryDef:
    code: str
    short_label: str  # компактный лейбл для кнопки (с эмодзи)
    long_label: str  # развёрнутая подпись (заголовок экрана)
    emoji: str


# Порядок — для UI. RPF и originals идут в конце как «специальные».
CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef("anime", "🎌 Аниме/манга", "Аниме и манга", "🎌"),
    CategoryDef("books", "📖 Книги", "Книги", "📖"),
    CategoryDef("films", "🎬 Фильмы", "Фильмы", "🎬"),
    CategoryDef("series", "📺 Сериалы", "Сериалы", "📺"),
    CategoryDef("cartoons", "🎨 Мульты", "Мультфильмы", "🎨"),
    CategoryDef("comics", "🦸 Комиксы", "Комиксы", "🦸"),
    CategoryDef("games", "🎮 Игры", "Видеоигры", "🎮"),
    CategoryDef("musicals", "🎭 Мюзиклы", "Мюзиклы и театр", "🎭"),
    CategoryDef("rpf", "🌟 RPF", "Известные люди (RPF)", "🌟"),
    CategoryDef("originals", "✨ Ориджиналы", "Ориджиналы", "✨"),
    CategoryDef("other", "📦 Другое", "Другое", "📦"),
)

CATEGORY_BY_CODE: dict[str, CategoryDef] = {c.code: c for c in CATEGORIES}

# Legacy mapping: исторически в БД были movies — отображаем как Фильмы.
_LEGACY_ALIAS = {"movies": "films"}


def get_category(code: str) -> CategoryDef:
    """Достать категорию по коду; legacy-коды (movies) маппятся на актуальные.

    Если код совершенно неизвестный — возвращаем 'other' как safe-fallback,
    чтобы ничего не падало в UI на исторических данных.
    """
    code = (code or "").strip().lower()
    code = _LEGACY_ALIAS.get(code, code)
    return CATEGORY_BY_CODE.get(code, CATEGORY_BY_CODE["other"])


def category_short_label(code: str) -> str:
    return get_category(code).short_label


def category_long_label(code: str) -> str:
    return get_category(code).long_label
