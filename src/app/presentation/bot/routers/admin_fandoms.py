"""Роутер админского CRUD фандомов."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.reference.fandoms_crud import (
    CreateFandomCommand,
    CreateFandomUseCase,
    ListFandomsAdminUseCase,
    UpdateFandomCommand,
    UpdateFandomUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.presentation.bot.callback_data.admin import AdminCD, FandomAdminCD
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.fsm.states.admin_fandoms import FandomCreateFlow
from app.presentation.bot.keyboards.admin_fandoms import (
    build_fandom_card_kb,
    build_fandoms_list_kb,
)
from app.presentation.bot.ui_helpers import render

log = get_logger(__name__)
router = Router(name="admin_fandoms")


async def _show_fandoms_list(
    *, event: CallbackQuery | Message, list_uc: ListFandomsAdminUseCase
) -> None:
    rows = await list_uc(active_only=False)
    items = [(int(r.id), str(r.name), bool(r.active)) for r in rows[:40]]
    await render(
        event,
        f"📚 <b>Фандомы</b> (всего: {len(rows)})",
        reply_markup=build_fandoms_list_kb(items),
        parse_mode="HTML",
    )


@router.callback_query(AdminCD.filter(F.action == "fandoms"), IsAdmin())
@router.callback_query(FandomAdminCD.filter(F.action == "list"), IsAdmin())
@inject
async def show_fandoms(
    cb: CallbackQuery,
    list_uc: FromDishka[ListFandomsAdminUseCase],
) -> None:
    await _show_fandoms_list(event=cb, list_uc=list_uc)
    await cb.answer()


from app.presentation.bot.fandom_categories import CATEGORIES as _CATEGORIES_TUPLE

_ALLOWED_CATEGORIES_RU: dict[str, str] = {cat.code: cat.short_label for cat in _CATEGORIES_TUPLE}


@router.callback_query(FandomAdminCD.filter(F.action == "new"), IsAdmin())
async def new_fandom_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FandomCreateFlow.waiting_name)
    await render(
        cb,
        "✏️ <b>Новый фандом</b> — шаг 1/3\n\n"
        "Пришли название (как будет отображаться, например «Гарри Поттер»):",
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(FandomCreateFlow.waiting_name, F.chat.type == "private", IsAdmin())
async def receive_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 256:
        await message.answer("❌ Название должно быть от 1 до 256 символов. Пришли ещё раз:")
        return
    await state.update_data(name=name)
    await state.set_state(FandomCreateFlow.waiting_category)
    code_list = ", ".join(f"<code>{c}</code>" for c in _ALLOWED_CATEGORIES_RU)
    options = " / ".join(_ALLOWED_CATEGORIES_RU.values())
    await message.answer(
        f"✏️ <b>Шаг 2/3</b> — категория.\n\nПришли одно из: {code_list}.\n\nВарианты: {options}",
        parse_mode="HTML",
    )


@router.message(FandomCreateFlow.waiting_category, F.chat.type == "private", IsAdmin())
async def receive_category(message: Message, state: FSMContext) -> None:
    cat = (message.text or "").strip().lower()
    if cat not in _ALLOWED_CATEGORIES_RU:
        await message.answer(
            "❌ Категория должна быть одной из: "
            + ", ".join(_ALLOWED_CATEGORIES_RU)
            + ". Пришли ещё раз:"
        )
        return
    await state.update_data(category=cat)
    await state.set_state(FandomCreateFlow.waiting_aliases)
    await message.answer(
        "✏️ <b>Шаг 3/3</b> — альтернативные названия.\n\n"
        "Через запятую, например: <i>HP, Harry Potter, ГП</i>.\n"
        "Если не нужно — пришли «-».",
        parse_mode="HTML",
    )


@router.message(FandomCreateFlow.waiting_aliases, F.chat.type == "private", IsAdmin())
@inject
async def receive_aliases(
    message: Message,
    state: FSMContext,
    uc: FromDishka[CreateFandomUseCase],
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    raw = (message.text or "").strip()
    aliases: list[str] = (
        [] if raw in {"-", ""} else [x.strip() for x in raw.split(",") if x.strip()]
    )

    try:
        row = await uc(
            CreateFandomCommand(
                actor_id=message.from_user.id,
                name=str(data.get("name") or ""),
                category=str(data.get("category") or ""),
                aliases=aliases,
            )
        )
    except DomainError as e:
        await message.answer(f"❌ {e}")
        await state.clear()
        return

    await state.clear()
    await message.answer(
        f"✅ Фандом создан:\n\n"
        f"  #{int(row.id)} «{escape(row.name)}»\n"
        f"  slug: <code>{escape(row.slug)}</code>\n"
        f"  категория: {_ALLOWED_CATEGORIES_RU.get(row.category, row.category)}\n"
        f"  alias'ов: {len(row.aliases)}",
        parse_mode="HTML",
    )


def _format_fandom_card(row: object) -> str:  # type: ignore[no-untyped-def]
    cat_label = _ALLOWED_CATEGORIES_RU.get(
        str(row.category),  # type: ignore[attr-defined]
        str(row.category),  # type: ignore[attr-defined]
    )
    return (
        f"📚 <b>#{int(row.id)} «{escape(str(row.name))}»</b>\n"  # type: ignore[attr-defined]
        f"slug: <code>{escape(str(row.slug))}</code>\n"  # type: ignore[attr-defined]
        f"Категория: {escape(cat_label)} (<code>{escape(str(row.category))}</code>)\n"  # type: ignore[attr-defined]
        f"Альтернативные названия: "
        f"{', '.join(escape(a) for a in row.aliases) if row.aliases else '—'}\n"  # type: ignore[attr-defined]
        f"Статус: {'активен' if row.active else 'выключен'}"  # type: ignore[attr-defined]
    )


@router.callback_query(FandomAdminCD.filter(F.action == "open"), IsAdmin())
@inject
async def open_fandom(
    cb: CallbackQuery,
    callback_data: FandomAdminCD,
    list_uc: FromDishka[ListFandomsAdminUseCase],
) -> None:
    rows = await list_uc(active_only=False)
    row = next((r for r in rows if int(r.id) == int(callback_data.fandom_id)), None)
    if row is None:
        await cb.answer("Фандом не найден.", show_alert=True)
        return
    await render(
        cb,
        _format_fandom_card(row),
        reply_markup=build_fandom_card_kb(int(row.id), active=row.active),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(FandomAdminCD.filter(F.action == "toggle_active"), IsAdmin())
@inject
async def toggle_fandom_active(
    cb: CallbackQuery,
    callback_data: FandomAdminCD,
    list_uc: FromDishka[ListFandomsAdminUseCase],
    update_uc: FromDishka[UpdateFandomUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    rows = await list_uc(active_only=False)
    row = next((r for r in rows if int(r.id) == int(callback_data.fandom_id)), None)
    if row is None:
        await cb.answer("Не найден.", show_alert=True)
        return
    try:
        await update_uc(
            UpdateFandomCommand(
                actor_id=cb.from_user.id,
                fandom_id=int(row.id),
                active=not row.active,
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    # Эмулируем обновлённую row, чтобы перерисовать карточку.
    updated = type(row)(
        id=row.id,
        slug=row.slug,
        name=row.name,
        category=row.category,
        aliases=row.aliases,
        active=not row.active,
    )
    await render(
        cb,
        _format_fandom_card(updated),
        reply_markup=build_fandom_card_kb(int(row.id), active=not row.active),
        parse_mode="HTML",
    )
    await cb.answer("✅ Обновлено")
