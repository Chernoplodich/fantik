"""Главное меню: placeholder-обработчики для пока не реализованных разделов."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.presentation.bot.texts.ru import t

router = Router(name="menu")


@router.callback_query(F.data == "menu:admin")
async def stub(cb: CallbackQuery) -> None:
    await cb.answer(t("not_implemented"), show_alert=True)
