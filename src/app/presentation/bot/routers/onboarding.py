"""Хэндлер принятия правил — финализирует онбординг."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka, inject

from app.application.users.agree_to_rules import (
    AgreeToRulesCommand,
    AgreeToRulesUseCase,
)
from app.domain.users.value_objects import Role
from app.presentation.bot.keyboards.main_menu import build_main_menu_kb
from app.presentation.bot.texts.ru import t

router = Router(name="onboarding")


@router.callback_query(F.data == "rules:accept")
@inject
async def on_rules_accept(
    cb: CallbackQuery,
    state: FSMContext,
    agree_uc: FromDishka[AgreeToRulesUseCase],
    role: Role = Role.USER,
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    await agree_uc(AgreeToRulesCommand(user_id=cb.from_user.id))
    await state.clear()
    await cb.message.answer(
        t("rules_accepted"),
        reply_markup=build_main_menu_kb(role=role, is_author=False),
    )
    await cb.answer("Готово!")
