"""Профиль пользователя и установка ника автора."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.users.delete_user import DeleteUserCommand, DeleteUserUseCase
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
from app.presentation.bot.fsm.states.profile import DeleteMeFlow
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


# ---------- /delete_me (self-deletion по запросу пользователя) ----------

_DELETE_WARNING = (
    "⚠️ <b>Удаление аккаунта</b>\n\n"
    "Будет удалено:\n"
    "• Все твои черновики и отклонённые работы (безвозвратно)\n"
    "• Закладки, лайки, прогресс чтения, подписки\n"
    "• Жалобы, которые ты оставлял\n\n"
    "Будет обезличено:\n"
    "• Опубликованные работы — останутся в каталоге под подписью «Удалённый пользователь»\n"
    "• Имя, фамилия, @username — очистим\n"
    "• Ник автора — заменим на <code>deleted_xxxxxxxx</code>\n\n"
    "После удаления войти под тем же Telegram-ID заново <b>нельзя</b> — аккаунт останется забанен.\n\n"
    "Подтверждаешь?"
)


def _build_delete_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Да, удалить навсегда",
                    callback_data="profile:delete_me:confirm",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="profile:delete_me:cancel")],
        ]
    )


@router.message(Command("delete_me"))
async def delete_me_entry(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.set_state(DeleteMeFlow.confirming)
    await message.answer(
        _DELETE_WARNING, parse_mode="HTML", reply_markup=_build_delete_confirm_kb()
    )


@router.callback_query(
    DeleteMeFlow.confirming, F.data == "profile:delete_me:cancel"
)
async def delete_me_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if cb.message is not None:
        try:
            await cb.message.edit_text("Удаление отменено.")
        except TelegramBadRequest:
            pass
    await cb.answer("Отменено")


@router.callback_query(
    DeleteMeFlow.confirming, F.data == "profile:delete_me:confirm"
)
@inject
async def delete_me_confirm(
    cb: CallbackQuery,
    state: FSMContext,
    delete_user: FromDishka[DeleteUserUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    await state.clear()
    try:
        await delete_user(DeleteUserCommand(user_id=cb.from_user.id))
    except Exception:
        await cb.answer("Не удалось удалить. Попробуй ещё раз или напиши админу.", show_alert=True)
        raise
    if cb.message is not None:
        try:
            await cb.message.edit_text(
                "Аккаунт удалён. Прощай. Опубликованные работы останутся в каталоге под подписью «Удалённый пользователь»."
            )
        except TelegramBadRequest:
            pass
    await cb.answer()


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
