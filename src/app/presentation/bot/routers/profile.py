"""Профиль пользователя и установка ника автора."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.users.ports import IUserRepository
from app.application.users.set_author_nick import (
    SetAuthorNickCommand,
    SetAuthorNickUseCase,
)
from app.core.errors import ValidationError
from app.domain.shared.types import UserId
from app.domain.users.exceptions import AuthorNickAlreadyTakenError
from app.domain.users.value_objects import Role
from app.presentation.bot.fsm.states.onboarding import AuthorNickFlow
from app.presentation.bot.keyboards.main_menu import (
    build_main_menu_kb,
    build_profile_kb,
)
from app.presentation.bot.texts.ru import t

router = Router(name="profile")


# ---------- Профиль ----------


@router.message(Command("profile"))
@router.callback_query(F.data == "menu:profile")
@inject
async def show_profile(
    event: Message | CallbackQuery,
    users: FromDishka[IUserRepository],
    role: Role = Role.USER,
) -> None:
    if event.from_user is None:
        return
    user = await users.get(UserId(event.from_user.id))
    if user is None:
        await _reply(event, "Пользователь не найден. Выполни /start.")
        return
    text = t(
        "profile_card",
        id=user.id,
        nick=f"<b>{user.author_nick}</b>" if user.author_nick else "—",
        role=user.role.value,
        created_at=user.created_at.strftime("%Y-%m-%d") if user.created_at else "—",
    )
    await _reply(
        event,
        text,
        parse_mode="HTML",
        reply_markup=build_profile_kb(is_author=user.is_author),
    )
    if isinstance(event, CallbackQuery):
        await event.answer()


# ---------- Назад в главное меню ----------


@router.callback_query(F.data == "menu:back")
@inject
async def back_to_menu(
    cb: CallbackQuery,
    users: FromDishka[IUserRepository],
    role: Role = Role.USER,
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    user = await users.get(UserId(cb.from_user.id))
    is_author = user.is_author if user else False
    try:
        await cb.message.edit_text(
            t("main_menu"),
            reply_markup=build_main_menu_kb(role=role, is_author=is_author),
        )
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
    await cb.answer()


# ---------- Установка ника ----------


@router.callback_query(F.data == "menu:become_author")
@inject
async def start_nick_flow(
    cb: CallbackQuery,
    state: FSMContext,
    users: FromDishka[IUserRepository],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    user = await users.get(UserId(cb.from_user.id))
    if user and user.author_nick is not None:
        await cb.message.answer(
            t("nick_already_set", nick=user.author_nick),
            parse_mode="HTML",
        )
        await cb.answer()
        return
    await state.set_state(AuthorNickFlow.waiting_nick)
    await cb.message.answer(t("nick_prompt"), parse_mode="HTML")
    await cb.answer()


@router.message(AuthorNickFlow.waiting_nick)
@inject
async def on_nick_submitted(
    message: Message,
    state: FSMContext,
    set_nick: FromDishka[SetAuthorNickUseCase],
    role: Role = Role.USER,
) -> None:
    if message.from_user is None or not message.text:
        return
    try:
        result = await set_nick(
            SetAuthorNickCommand(user_id=message.from_user.id, nick=message.text)
        )
    except ValidationError:
        await message.answer(t("nick_invalid"))
        return
    except AuthorNickAlreadyTakenError:
        await message.answer(t("nick_taken"))
        return
    await state.clear()
    await message.answer(
        t("nick_set_success", nick=result.nick),
        parse_mode="HTML",
        reply_markup=build_main_menu_kb(role=role, is_author=True),
    )


# ---------- утилиты ----------


async def _reply(event: Message | CallbackQuery, text: str, **kwargs: object) -> None:
    """Для команды /profile — отправить новое сообщение.
    Для callback-кнопки «Профиль» — отредактировать текущее сообщение меню,
    чтобы чат не засорялся дубликатами."""
    if isinstance(event, CallbackQuery):
        assert event.message is not None
        try:
            await event.message.edit_text(text, **kwargs)  # type: ignore[arg-type]
        except TelegramBadRequest as exc:
            # "message is not modified" — игнорируем (пользователь нажал кнопку повторно)
            if "not modified" not in str(exc).lower():
                raise
    else:
        await event.answer(text, **kwargs)  # type: ignore[arg-type]
