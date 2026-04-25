"""Раскладка админ-меню: тематические группы + рабочая кнопка «Назад».

Регрессии:
- Кнопка «◀︎ Главное меню» должна иметь callback `menu:back` (универсальный,
  обрабатывается в profile.back_to_menu). Раньше был `menu:main`, без обработчика.
- Шесть разделов сгруппированы: рассылки+трекинг, статистика, фандомы+заявки,
  теги, обратно. Это удобнее, чем 7 кнопок столбцом.
"""

from __future__ import annotations

from app.presentation.bot.keyboards.admin_menu import build_admin_menu_kb


def _row_texts(kb: object) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        rows.append([btn.text for btn in row])
    return rows


def _row_callbacks(kb: object) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        rows.append([btn.callback_data or "" for btn in row])
    return rows


class TestAdminMenuLayout:
    def test_back_button_uses_universal_menu_back_callback(self) -> None:
        """Регрессия: callback должен быть `menu:back`, иначе из админки не выйти."""
        kb = build_admin_menu_kb()
        callbacks = [cb for row in _row_callbacks(kb) for cb in row]
        assert "menu:back" in callbacks
        assert "menu:main" not in callbacks

    def test_thematic_grouping_2_1_2_1_1(self) -> None:
        """Группировка: рассылки+трекинг, статистика, фандомы+заявки, теги, назад."""
        rows = _row_texts(build_admin_menu_kb())
        sizes = [len(r) for r in rows]
        assert sizes == [2, 1, 2, 1, 1]

    def test_first_row_is_messaging_group(self) -> None:
        rows = _row_texts(build_admin_menu_kb())
        # Первая пара — операционные коммуникации.
        assert "Рассылки" in rows[0][0]
        assert "Трекинг" in rows[0][1]

    def test_third_row_is_taxonomy_group(self) -> None:
        rows = _row_texts(build_admin_menu_kb())
        # Третья пара — справочники: фандомы + заявки.
        assert "Фандомы" in rows[2][0]
        assert "Заявки" in rows[2][1]

    def test_back_button_is_last(self) -> None:
        rows = _row_texts(build_admin_menu_kb())
        assert "Главное меню" in rows[-1][0]
