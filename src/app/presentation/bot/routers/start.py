"""Хэндлеры /start и /help: регистрация + парсинг UTM/deep-link."""

from __future__ import annotations

import re

from aiogram import Router, html
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.users.register_user import RegisterUserCommand, RegisterUserUseCase
from app.core.logging import get_logger
from app.domain.users.value_objects import Role
from app.presentation.bot.callback_data.reader import ReadNav
from app.presentation.bot.fsm.states.onboarding import Onboarding
from app.presentation.bot.keyboards.main_menu import (
    build_main_menu_kb,
    build_rules_accept_kb,
)
from app.presentation.bot.texts.ru import t

log = get_logger(__name__)
router = Router(name="start")

_CODE_RE = re.compile(r"^[A-Za-z0-9]{6,16}$")
_FIC_RE = re.compile(r"^fic_(\d+)$")


def _parse_payload(payload: str) -> tuple[str | None, str | None]:
    """Разбор аргумента /start.
    Возвращает (utm_code, special) — одно из двух либо оба None."""
    payload = payload.strip()
    if not payload:
        return None, None
    m = _FIC_RE.fullmatch(payload)
    if m:
        return None, f"fic_{m.group(1)}"
    if _CODE_RE.fullmatch(payload):
        return payload, None
    return None, None


@router.message(CommandStart())
@inject
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    register_uc: FromDishka[RegisterUserUseCase],
    role: Role = Role.USER,
) -> None:
    if message.from_user is None:  # защитный кейс
        return

    utm_code, special = _parse_payload(command.args or "")

    result = await register_uc(
        RegisterUserCommand(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
            utm_code=utm_code,
        )
    )

    log.info(
        "user_start",
        tg_id=message.from_user.id,
        is_new=result.is_new,
        utm_code=utm_code,
        special=special,
    )

    if result.user.agreed_at is None:
        # Онбординг: правила
        await message.answer(
            t("welcome_new"),
            parse_mode=None,
        )
        await message.answer(
            t("rules_short"),
            parse_mode="HTML",
            reply_markup=build_rules_accept_kb(),
        )
        await state.set_state(Onboarding.waiting_rules_acceptance)
        return

    # Уже прошёл онбординг → главное меню
    if special and special.startswith("fic_"):
        fic_id_str = special[4:]
        try:
            fic_id = int(fic_id_str)
        except ValueError:
            fic_id = 0
        if fic_id > 0:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📖 Открыть",
                            callback_data=ReadNav(a="open", f=fic_id).pack(),
                        )
                    ]
                ]
            )
            await message.answer("Открываю работу…", reply_markup=kb)
            return

    await message.answer(
        t("welcome_back"),
        reply_markup=build_main_menu_kb(role=role, is_author=result.user.is_author),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — главное меню\n"
        "/help — эта справка\n\n"
        f"Код версии: {html.code('fantik v0.1')}",
        parse_mode="HTML",
    )
