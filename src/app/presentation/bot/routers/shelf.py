"""Роутер «Моей полки»: недавнее / закладки / лайки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.reading.list_my_shelf import (
    ListMyShelfCommand,
    ListMyShelfUseCase,
    ShelfKind,
)
from app.presentation.bot.callback_data.shelf import ShelfCD
from app.presentation.bot.keyboards.shelf import shelf_list_kb

router = Router(name="shelf")

_SHELF_HEADER = {
    ShelfKind.RECENT: "🕒 Недавно читал",
    ShelfKind.BOOKMARKS: "📑 Закладки",
    ShelfKind.LIKES: "❤️ Лайки",
}


async def _render(
    cb_or_msg: CallbackQuery | Message,
    kind: ShelfKind,
    uc: ListMyShelfUseCase,
    user_id: int,
) -> None:
    items = await uc(ListMyShelfCommand(user_id=user_id, kind=kind, limit=20, offset=0))
    header = _SHELF_HEADER[kind]
    if not items:
        body = f"{header}\n\nПусто."
    else:
        lines = [header, ""]
        for idx, it in enumerate(items, start=1):
            suffix = ""
            if (
                kind == ShelfKind.RECENT
                and it.chapter_number is not None
                and it.page_no is not None
            ):
                suffix = f" · гл.{it.chapter_number} стр.{it.page_no}"
            lines.append(f"{idx}. {it.title}{suffix}")
        body = "\n".join(lines)

    kb = shelf_list_kb(active=kind.value, items=items)

    if isinstance(cb_or_msg, CallbackQuery):
        if cb_or_msg.message is None:
            return
        try:
            await cb_or_msg.message.edit_text(body, reply_markup=kb)  # type: ignore[union-attr]
        except Exception:
            await cb_or_msg.message.answer(body, reply_markup=kb)
    else:
        await cb_or_msg.answer(body, reply_markup=kb)


@router.message(Command("shelf"))
@router.callback_query(F.data == "menu:shelf")
@inject
async def shelf_root(
    event: Message | CallbackQuery,
    uc: FromDishka[ListMyShelfUseCase],
) -> None:
    user_id = event.from_user.id if event.from_user else 0
    if isinstance(event, CallbackQuery):
        await _render(event, ShelfKind.RECENT, uc, user_id)
        await event.answer()
    else:
        await _render(event, ShelfKind.RECENT, uc, user_id)


@router.callback_query(ShelfCD.filter(F.a.in_({"recent", "bookmarks", "likes"})))
@inject
async def shelf_tab(
    cb: CallbackQuery,
    callback_data: ShelfCD,
    uc: FromDishka[ListMyShelfUseCase],
) -> None:
    kind = ShelfKind(callback_data.a)
    await _render(cb, kind, uc, cb.from_user.id)
    await cb.answer()
