"""FSM админ-фандомов:

- `FandomCreateFlow` — создание нового фандома: категория (picker) → name → aliases.
  Состояние `waiting_category` пропускается, если админ нажал «➕ Новый в [категория]».
- `FandomEditFlow` — редактирование name/aliases у существующего фандома.
- `FandomSearchFlow` — ввод текстового запроса для поиска по фандомам.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class FandomCreateFlow(StatesGroup):
    waiting_category = State()
    waiting_name = State()
    waiting_aliases = State()


class FandomEditFlow(StatesGroup):
    waiting_new_name = State()
    waiting_new_aliases = State()


class FandomSearchFlow(StatesGroup):
    waiting_query = State()
