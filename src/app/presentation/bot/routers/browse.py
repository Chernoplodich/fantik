"""Каталог: /catalog + ленты «Новое» / «Топ» / «По фэндому»."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.fanfics.ports import IReferenceReader
from app.application.reading.list_feed import (
    FeedKind,
    ListFeedCommand,
    ListFeedUseCase,
)
from app.core.logging import get_logger
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.browse import BrowseCD
from app.presentation.bot.keyboards.browse import (
    browse_root_kb,
    fandom_pick_kb,
)
from app.presentation.bot.keyboards.reader import feed_kb

log = get_logger(__name__)
router = Router(name="browse")

_PAGE_SIZE = 10
_FANDOMS_PER_PAGE = 12


# ---------- root ----------


@router.message(Command("catalog"))
async def cmd_catalog(message: Message) -> None:
    await message.answer("📚 Каталог работ", reply_markup=browse_root_kb())


@router.callback_query(F.data == "menu:browse")
@router.callback_query(BrowseCD.filter(F.a == "root"))
async def show_root(cb: CallbackQuery) -> None:
    if cb.message is None:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            "📚 Каталог работ", reply_markup=browse_root_kb()
        )
    except Exception:  # noqa: BLE001 — edit может упасть (например, на photo)
        await cb.message.answer("📚 Каталог работ", reply_markup=browse_root_kb())
    await cb.answer()


# ---------- feed: new / top ----------


async def _render_feed(
    cb: CallbackQuery,
    kind: FeedKind,
    fandom_id: int,
    page: int,
    list_feed: ListFeedUseCase,
    reference: IReferenceReader,
) -> None:
    items = await list_feed(
        ListFeedCommand(
            kind=kind,
            fandom_id=fandom_id or None,
            limit=_PAGE_SIZE,
            offset=page * _PAGE_SIZE,
        )
    )
    # has_more оцениваем по полноте страницы (эвристика; точный total — в Этапе 4).
    has_more = len(items) == _PAGE_SIZE

    header_parts: list[str] = []
    header_parts.append("🆕 Новое" if kind == FeedKind.NEW else "🔥 Топ")
    if fandom_id:
        fandom = await reference.get_fandom(FandomId(fandom_id))
        if fandom is not None:
            header_parts.append(f"· {fandom.name}")
    header = " ".join(header_parts)

    if not items:
        body = f"{header}\n\nПока нет работ."
    else:
        lines = [header, ""]
        for idx, it in enumerate(items, start=page * _PAGE_SIZE + 1):
            author = f" — {it.author_nick}" if it.author_nick else ""
            lines.append(
                f"{idx}. {it.title}{author} · ❤️ {it.likes_count} · 📖 {it.chapters_count} гл."
            )
        body = "\n".join(lines)

    kb = feed_kb(
        items=items,
        kind=kind.value,
        fandom_id=fandom_id,
        page=page,
        has_more=has_more,
    )
    if cb.message is not None:
        try:
            await cb.message.edit_text(body, reply_markup=kb)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            await cb.message.answer(body, reply_markup=kb)


@router.callback_query(BrowseCD.filter(F.a == "new"))
@inject
async def show_new(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    list_feed: FromDishka[ListFeedUseCase],
    reference: FromDishka[IReferenceReader],
) -> None:
    await _render_feed(cb, FeedKind.NEW, callback_data.fd, callback_data.pg, list_feed, reference)
    await cb.answer()


@router.callback_query(BrowseCD.filter(F.a == "top"))
@inject
async def show_top(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    list_feed: FromDishka[ListFeedUseCase],
    reference: FromDishka[IReferenceReader],
) -> None:
    await _render_feed(cb, FeedKind.TOP, callback_data.fd, callback_data.pg, list_feed, reference)
    await cb.answer()


# ---------- by_fandom: pick → feed ----------


@router.callback_query(BrowseCD.filter(F.a == "by_fandom"))
@router.callback_query(BrowseCD.filter(F.a == "fd_page"))
@inject
async def pick_fandom(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    reference: FromDishka[IReferenceReader],
) -> None:
    page = callback_data.pg
    fandoms, total = await reference.list_fandoms_paginated(
        limit=_FANDOMS_PER_PAGE, offset=page * _FANDOMS_PER_PAGE, active_only=True
    )
    has_more = (page + 1) * _FANDOMS_PER_PAGE < total
    if cb.message is not None:
        try:
            await cb.message.edit_text(  # type: ignore[union-attr]
                "🏷 Выбери фэндом:",
                reply_markup=fandom_pick_kb(fandoms=fandoms, page=page, has_more=has_more),
            )
        except Exception:  # noqa: BLE001
            await cb.message.answer(
                "🏷 Выбери фэндом:",
                reply_markup=fandom_pick_kb(fandoms=fandoms, page=page, has_more=has_more),
            )
    await cb.answer()


@router.callback_query(BrowseCD.filter(F.a == "fandom"))
@inject
async def show_fandom_feed(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    list_feed: FromDishka[ListFeedUseCase],
    reference: FromDishka[IReferenceReader],
) -> None:
    await _render_feed(cb, FeedKind.NEW, callback_data.fd, callback_data.pg, list_feed, reference)
    await cb.answer()
