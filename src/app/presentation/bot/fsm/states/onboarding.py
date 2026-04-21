"""FSM онбординга: ожидание согласия, ввод ника."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    waiting_rules_acceptance = State()


class AuthorNickFlow(StatesGroup):
    waiting_nick = State()
