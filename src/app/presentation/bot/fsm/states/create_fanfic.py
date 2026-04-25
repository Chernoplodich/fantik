"""FSM для создания нового фика (автор)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CreateFanficStates(StatesGroup):
    waiting_title = State()
    waiting_summary = State()
    waiting_fandom = State()  # экран выбора (категории/категория/поиск/предложение)
    waiting_fandom_search = State()  # пользователь вводит подстроку названия
    waiting_fandom_proposal_name = State()  # ввод названия для предложения
    waiting_fandom_proposal_category = State()  # выбор категории для предложения
    waiting_age_rating = State()
    waiting_tags = State()
    waiting_cover = State()
    chapter_or_submit = State()
    waiting_chapter_title = State()
    waiting_chapter_text = State()
