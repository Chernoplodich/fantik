"""Callback-data для поисковых фильтров и результатов.

Поля:
- `a` action: filters_root / pick_fandom (категории) / cat (фандомы в категории) /
  fsearch (войти во ввод подстроки) / propose (предложить новый фандом) /
  pick_age / pick_tag / toggle / set_sort / apply / reset / page / open /
  enter_q (войти во ввод запроса) / clear_q
- `k` kind: 'fandom' | 'age' | 'tag' | '' (для action=toggle)
- `v` value: id фандома / код возраста / slug тега / сортировка / код категории
- `pg` page offset (страница списка выбора или страница результатов)

Общий лимит Telegram на callback_data — 64 байта; поэтому поля короткие.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class SearchCD(CallbackData, prefix="s"):
    a: str
    k: str = ""
    v: str = ""
    pg: int = 0
