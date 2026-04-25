"""FSM-состояния для поискового флоу.

Храним выбранные фильтры в FSMContext-data (Redis) — позволяет пережить
переходы между меню без раздувания callback_data.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SearchFiltersFSM(StatesGroup):
    selecting = State()  # пользователь открыл меню и переключает фильтры
    browsing = State()  # пользователь листает результаты
    entering_query = State()  # пользователь вводит свободный q
    entering_fandom_search = State()  # пользователь вводит подстроку фандома
