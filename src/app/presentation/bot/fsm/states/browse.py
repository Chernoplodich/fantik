"""FSM-состояния просмотра каталога.

Сейчас единственное состояние — ввод подстроки в пикере «🎭 По фэндому»
(аналог `entering_fandom_search` из расширенного поиска, но без чекбоксов:
выбор фандома сразу открывает ленту).
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BrowseStates(StatesGroup):
    entering_fandom_search = State()
