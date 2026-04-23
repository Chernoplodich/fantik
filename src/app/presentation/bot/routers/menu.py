"""Главное меню: admin-корень + placeholder-обработчики для не реализованных разделов."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.presentation.bot.callback_data.admin import AdminCD
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.keyboards.admin_menu import build_admin_menu_kb
from app.presentation.bot.ui_helpers import render

router = Router(name="menu")

_ADMIN_MENU_TEXT = "⚙️ <b>Админ-меню</b>\n\nВыбери раздел:"


@router.message(Command("admin"), IsAdmin())
async def admin_command(message: Message) -> None:
    await message.answer(
        _ADMIN_MENU_TEXT,
        reply_markup=build_admin_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:admin", IsAdmin())
@router.callback_query(AdminCD.filter(F.action == "root"), IsAdmin())
async def open_admin_menu(cb: CallbackQuery) -> None:
    await render(
        cb,
        _ADMIN_MENU_TEXT,
        reply_markup=build_admin_menu_kb(),
        parse_mode="HTML",
    )
    await cb.answer()
