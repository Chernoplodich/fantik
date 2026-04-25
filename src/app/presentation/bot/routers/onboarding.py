"""Хэндлер принятия правил — финализирует онбординг."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
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

    # Сами правила оставляем в чате — редактируем исходное сообщение, дописывая
    # снизу маркер согласия и убирая кнопку. parse_mode="HTML" — у исходного
    # `rules_short` тоже HTML.
    original_text = cb.message.html_text if cb.message.text else ""
    new_text = original_text + t("rules_accepted_marker")
    try:
        await cb.message.edit_text(new_text, parse_mode="HTML", reply_markup=None)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise

    # Главное меню — отдельным сообщением снизу.
    await cb.message.answer(
        t("rules_accepted"),
        reply_markup=build_main_menu_kb(role=role, is_author=False),
    )
    await cb.answer("Готово!")
