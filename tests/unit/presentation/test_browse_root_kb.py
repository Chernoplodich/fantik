"""Раскладка корня каталога после UX-итерации: один экран с прогрессивным раскрытием.

Главный CTA — «✏️ Найти по слову». Под ним — 🆕 Новое + 🔥 Топ + 🎭 По фэндому.
В самом низу — «🔧 Расширенный поиск» (фильтры). Длинный текст-инструкция убран.
"""

from __future__ import annotations

from app.presentation.bot.keyboards.browse import browse_root_kb


def _flatten(kb: object) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        rows.append([btn.text for btn in row])
    return rows


def test_browse_root_has_quick_search_first() -> None:
    rows = _flatten(browse_root_kb())
    # Первая строка — большая кнопка быстрого поиска.
    assert rows[0] == ["✏️ Найти по слову"]


def test_browse_root_has_feeds_in_one_row() -> None:
    rows = _flatten(browse_root_kb())
    # Где-то в раскладке должна быть строка «🆕 Новое + 🔥 Топ» (2 в ряд).
    assert ["🆕 Новое", "🔥 Топ"] in rows


def test_browse_root_has_advanced_search_renamed() -> None:
    rows = _flatten(browse_root_kb())
    flat = [t for row in rows for t in row]
    # «Фильтры» из старой версии заменены на «🔧 Расширенный поиск».
    assert "🔧 Расширенный поиск" in flat
    assert "🔎 Фильтры" not in flat


def test_browse_root_keeps_back_to_main_menu() -> None:
    rows = _flatten(browse_root_kb())
    # Последняя строка — выход в главное меню.
    assert rows[-1] == ["← Главное меню"]
