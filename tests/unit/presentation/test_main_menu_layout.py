"""Раскладка главного меню для разных ролей.

Регрессия плана: для ADMIN кнопки 🛡 Модерация и ⚙️ Админ должны быть
в одной строке (раньше были в двух). Для MODERATOR — одна кнопка 🛡 Модерация
без админ-кнопки. Для USER — обе кнопки скрыты.
"""

from __future__ import annotations

from app.domain.users.value_objects import Role
from app.presentation.bot.keyboards.main_menu import build_main_menu_kb


def _row_texts(kb: object) -> list[list[str]]:
    """Достать тексты кнопок построчно. Совместимо с aiogram InlineKeyboardMarkup."""
    rows: list[list[str]] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        rows.append([btn.text for btn in row])
    return rows


class TestMainMenuLayout:
    def test_user_sees_no_mod_or_admin_buttons(self) -> None:
        kb = build_main_menu_kb(role=Role.USER, is_author=False)
        rows = _row_texts(kb)
        flat = [t for row in rows for t in row]
        assert "🛡 Модерация" not in flat
        assert "⚙️ Админ" not in flat

    def test_moderator_sees_only_moderation(self) -> None:
        kb = build_main_menu_kb(role=Role.MODERATOR, is_author=True)
        rows = _row_texts(kb)
        # Последняя строка должна содержать ровно «🛡 Модерация»
        assert rows[-1] == ["🛡 Модерация"]
        flat = [t for row in rows for t in row]
        assert "⚙️ Админ" not in flat

    def test_admin_sees_both_in_same_row(self) -> None:
        kb = build_main_menu_kb(role=Role.ADMIN, is_author=True)
        rows = _row_texts(kb)
        # Должна быть строка ровно с двумя кнопками — Модерация + Админ.
        last_row = rows[-1]
        assert last_row == ["🛡 Модерация", "⚙️ Админ"]

    def test_admin_without_authorship_layout_is_valid(self) -> None:
        # Корнер-кейс: ADMIN без author_nick — нет «Мои работы», но обе админ-кнопки в ряд.
        kb = build_main_menu_kb(role=Role.ADMIN, is_author=False)
        rows = _row_texts(kb)
        last_row = rows[-1]
        assert last_row == ["🛡 Модерация", "⚙️ Админ"]
        flat = [t for row in rows for t in row]
        assert "✍️ Стать автором" in flat
