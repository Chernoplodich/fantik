"""Клавиатуры каталога.

Корневая `browse_root_kb` — главный экран каталога. Пикер «🎭 По фэндому»
теперь живёт в общем `keyboards/fandom_picker.py` (`flow="browse"`),
поэтому отдельной плоской клавиатуры здесь больше нет.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.browse import BrowseCD, QuickQCD


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def browse_root_kb() -> InlineKeyboardMarkup:
    """Корень каталога: один экран с прогрессивным раскрытием.

    Сверху — самый частый сценарий (текстовый поиск). Под ним — готовые
    подборки и выбор фандома. «🔧 Расширенный поиск» открывает фильтры
    тем, кому нужны точные комбинации — большинству юзеров не нужно.
    """
    # Локальный импорт: избегаем циклов при инициализации модулей keyboards/*.
    from app.presentation.bot.callback_data.search import SearchCD

    b = InlineKeyboardBuilder()
    # Главный CTA — текстовый поиск (одна большая кнопка).
    b.row(_btn("✏️ Найти по слову", QuickQCD(a="start").pack()))
    # Готовые подборки — самое популярное.
    b.row(
        _btn("🆕 Новое", BrowseCD(a="new").pack()),
        _btn("🔥 Топ", BrowseCD(a="top").pack()),
    )
    b.row(_btn("🎭 По фэндому", BrowseCD(a="by_fandom").pack()))
    # Только для тех кому нужны точные фильтры — спрятано отдельной кнопкой.
    b.row(_btn("🔧 Расширенный поиск", SearchCD(a="filters_root").pack()))
    b.row(_btn("← Главное меню", "menu:back"))
    return b.as_markup()


