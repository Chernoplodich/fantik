"""Раскладка меню модерации: 2 в первом ряду + назад.

Регрессия: «🎯 Следующая работа» и «Жалобы» должны быть в одной строке —
до этого было 3 кнопки столбцом.
"""

from __future__ import annotations

from app.presentation.bot.keyboards.moderation import build_mod_menu_kb


def _row_texts(kb: object) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        rows.append([btn.text for btn in row])
    return rows


class TestModMenuLayout:
    def test_first_row_has_two_buttons(self) -> None:
        rows = _row_texts(build_mod_menu_kb())
        assert len(rows[0]) == 2
        assert "Следующая работа" in rows[0][0]

    def test_second_row_is_back(self) -> None:
        rows = _row_texts(build_mod_menu_kb())
        assert len(rows[1]) == 1
        assert "Главное меню" in rows[1][0]

    def test_back_uses_menu_back_callback(self) -> None:
        kb = build_mod_menu_kb()
        callbacks = [
            btn.callback_data
            for row in kb.inline_keyboard  # type: ignore[attr-defined]
            for btn in row
        ]
        assert "menu:back" in callbacks
