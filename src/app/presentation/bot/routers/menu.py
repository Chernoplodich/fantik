"""Главное меню: обработчики кнопок-placeholder'ов (для Этапов 2+)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.presentation.bot.texts.ru import t

router = Router(name="menu")


@router.callback_query(
    F.data.in_({"menu:browse", "menu:shelf", "menu:my_works", "menu:new_fic", "menu:mod", "menu:admin"})
)
async def stub(cb: CallbackQuery) -> None:
    await cb.answer(t("not_implemented"), show_alert=True)
