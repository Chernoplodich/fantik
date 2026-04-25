"""Роутер админ-панели фандомов: двухступенчатая навигация + поиск.

Структура UX:
- `/admin → 📚 Фандомы` → корень: список 11 категорий с счётчиками.
- Клик категории → пагинированный список фандомов.
- 🔍 Найти по названию → FSM ввод запроса → результаты.
- Клик фандома → карточка (toggle / rename / aliases / back).
- ➕ Новый фандом → picker категорий → ввод имени → ввод aliases.
- ➕ Новый в [категория] (из списка категории) → пропуск выбора категории.
"""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.reference.fandoms_crud import (
    ALLOWED_CATEGORIES,
    CategoryStatsAdminUseCase,
    CreateFandomCommand,
    CreateFandomUseCase,
    ListFandomsByCategoryAdminUseCase,
    SearchFandomsAdminUseCase,
    UpdateFandomCommand,
    UpdateFandomUseCase,
)
from app.application.reference.ports import FandomAdminRow, IFandomAdminRepository
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.admin import AdminCD
from app.presentation.bot.callback_data.admin_fandoms import FdAdmCD
from app.presentation.bot.fandom_categories import (
    CATEGORY_BY_CODE,
    category_long_label,
    category_short_label,
)
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.fsm.states.admin_fandoms import (
    FandomCreateFlow,
    FandomEditFlow,
    FandomSearchFlow,
)
from app.presentation.bot.keyboards.admin_fandoms import (
    PAGE_SIZE,
    build_admin_create_categories_kb,
    build_admin_fandom_card_kb,
    build_admin_fandom_categories_kb,
    build_admin_fandoms_back_kb,
    build_admin_fandoms_in_category_kb,
    build_admin_search_results_kb,
)
from app.presentation.bot.ui_helpers import render

log = get_logger(__name__)
router = Router(name="admin_fandoms")


# ============================================================
# Helpers
# ============================================================


def _format_card(row: FandomAdminRow) -> str:
    cat_label = category_long_label(row.category)
    return (
        f"📚 <b>#{int(row.id)} «{escape(row.name)}»</b>\n"
        f"slug: <code>{escape(row.slug)}</code>\n"
        f"Категория: {escape(cat_label)} (<code>{escape(row.category)}</code>)\n"
        f"Альтернативные названия: "
        f"{', '.join(escape(a) for a in row.aliases) if row.aliases else '—'}\n"
        f"Статус: {'активен' if row.active else 'выключен'}"
    )


def _ensure_known_category(cat: str) -> bool:
    return cat in CATEGORY_BY_CODE or cat in ALLOWED_CATEGORIES


# ============================================================
# Шаг 1: корень — список категорий
# ============================================================


@router.callback_query(AdminCD.filter(F.action == "fandoms"), IsAdmin())
@router.callback_query(FdAdmCD.filter(F.a == "root"), IsAdmin())
@inject
async def show_categories(
    cb: CallbackQuery,
    state: FSMContext,
    stats_uc: FromDishka[CategoryStatsAdminUseCase],
) -> None:
    await state.clear()
    counts = await stats_uc()
    total = sum(counts.values())
    body = (
        "📚 <b>Управление фандомами</b>\n\n"
        f"Всего активных: <b>{total}</b>\n"
        "Выбери категорию, чтобы увидеть фандомы, или используй поиск."
    )
    await render(cb, body, reply_markup=build_admin_fandom_categories_kb(counts), parse_mode="HTML")
    await cb.answer()


# ============================================================
# Шаг 2: фандомы внутри категории
# ============================================================


@router.callback_query(FdAdmCD.filter(F.a == "cat"), IsAdmin())
@inject
async def show_category(
    cb: CallbackQuery,
    callback_data: FdAdmCD,
    state: FSMContext,
    list_uc: FromDishka[ListFandomsByCategoryAdminUseCase],
) -> None:
    await state.clear()
    cat = callback_data.cat
    if not _ensure_known_category(cat):
        await cb.answer("Неизвестная категория.", show_alert=True)
        return
    page = max(0, int(callback_data.pg))
    items, total = await list_uc(category=cat, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    has_more = (page + 1) * PAGE_SIZE < total
    long_label = category_long_label(cat)
    body = (
        f"<b>{escape(long_label)}</b>\n\n"
        f"Всего: <b>{total}</b>\n"
        f"Страница: {page + 1} из {max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)}"
    )
    if not items:
        body += "\n\n<i>В этой категории пока нет фандомов.</i>"
    await render(
        cb,
        body,
        reply_markup=build_admin_fandoms_in_category_kb(
            cat=cat, items=items, page=page, has_more=has_more
        ),
        parse_mode="HTML",
    )
    await cb.answer()


# ============================================================
# Карточка фандома
# ============================================================


@router.callback_query(FdAdmCD.filter(F.a == "open"), IsAdmin())
@inject
async def open_fandom(
    cb: CallbackQuery,
    callback_data: FdAdmCD,
    state: FSMContext,
    repo: FromDishka[IFandomAdminRepository],
) -> None:
    await state.clear()
    row = await repo.get(FandomId(int(callback_data.fid)))
    if row is None:
        await cb.answer("Фандом не найден.", show_alert=True)
        return
    cat_for_back = callback_data.cat or row.category
    await render(
        cb,
        _format_card(row),
        reply_markup=build_admin_fandom_card_kb(
            fid=int(row.id), cat=cat_for_back, active=row.active
        ),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(FdAdmCD.filter(F.a == "toggle"), IsAdmin())
@inject
async def toggle_active(
    cb: CallbackQuery,
    callback_data: FdAdmCD,
    repo: FromDishka[IFandomAdminRepository],
    update_uc: FromDishka[UpdateFandomUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()  # type: ignore[unreachable]
        return
    row = await repo.get(FandomId(int(callback_data.fid)))
    if row is None:
        await cb.answer("Не найден.", show_alert=True)
        return
    try:
        updated = await update_uc(
            UpdateFandomCommand(
                actor_id=cb.from_user.id,
                fandom_id=int(row.id),
                active=not row.active,
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    cat_for_back = callback_data.cat or updated.category
    await render(
        cb,
        _format_card(updated),
        reply_markup=build_admin_fandom_card_kb(
            fid=int(updated.id), cat=cat_for_back, active=updated.active
        ),
        parse_mode="HTML",
    )
    await cb.answer("✅ Обновлено")


# ============================================================
# Переименование фандома (FSM)
# ============================================================


@router.callback_query(FdAdmCD.filter(F.a == "rename"), IsAdmin())
async def start_rename(
    cb: CallbackQuery,
    callback_data: FdAdmCD,
    state: FSMContext,
) -> None:
    await state.set_state(FandomEditFlow.waiting_new_name)
    await state.update_data(fid=int(callback_data.fid), cat=callback_data.cat)
    await render(
        cb,
        "✏️ <b>Новое название</b>\n\nПришли новое имя фандома (1–256 символов).",
        reply_markup=build_admin_fandoms_back_kb(cat=callback_data.cat),
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(FandomEditFlow.waiting_new_name, F.chat.type == "private", IsAdmin())
@inject
async def receive_new_name(
    message: Message,
    state: FSMContext,
    update_uc: FromDishka[UpdateFandomUseCase],
    repo: FromDishka[IFandomAdminRepository],
) -> None:
    if message.from_user is None:
        return
    name = (message.text or "").strip()
    if not name or len(name) > 256:
        await message.answer("❌ Название должно быть от 1 до 256 символов. Пришли ещё раз:")
        return
    data = await state.get_data()
    fid = int(data.get("fid") or 0)
    cat = str(data.get("cat") or "")
    if not fid:
        await state.clear()
        await message.answer("❌ Сессия редактирования утеряна. Открой карточку заново.")
        return
    try:
        updated = await update_uc(
            UpdateFandomCommand(actor_id=message.from_user.id, fandom_id=fid, name=name)
        )
    except DomainError as e:
        await message.answer(f"❌ {e}")
        return
    await state.clear()
    row = await repo.get(FandomId(int(updated.id)))
    if row is None:
        await message.answer("❌ Не найден после правки.")
        return
    cat_for_back = cat or row.category
    await message.answer(
        _format_card(row),
        reply_markup=build_admin_fandom_card_kb(
            fid=int(row.id), cat=cat_for_back, active=row.active
        ),
        parse_mode="HTML",
    )


# ============================================================
# Правка aliases (FSM)
# ============================================================


@router.callback_query(FdAdmCD.filter(F.a == "aliases"), IsAdmin())
async def start_aliases_edit(
    cb: CallbackQuery,
    callback_data: FdAdmCD,
    state: FSMContext,
) -> None:
    await state.set_state(FandomEditFlow.waiting_new_aliases)
    await state.update_data(fid=int(callback_data.fid), cat=callback_data.cat)
    await render(
        cb,
        "✏️ <b>Альтернативные названия</b>\n\n"
        "Пришли через запятую (например: <i>HP, Harry Potter, ГП</i>).\n"
        "Чтобы очистить — пришли «-».",
        reply_markup=build_admin_fandoms_back_kb(cat=callback_data.cat),
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(FandomEditFlow.waiting_new_aliases, F.chat.type == "private", IsAdmin())
@inject
async def receive_new_aliases(
    message: Message,
    state: FSMContext,
    update_uc: FromDishka[UpdateFandomUseCase],
    repo: FromDishka[IFandomAdminRepository],
) -> None:
    if message.from_user is None:
        return
    raw = (message.text or "").strip()
    aliases = [] if raw in {"-", ""} else [x.strip() for x in raw.split(",") if x.strip()]
    data = await state.get_data()
    fid = int(data.get("fid") or 0)
    cat = str(data.get("cat") or "")
    if not fid:
        await state.clear()
        await message.answer("❌ Сессия редактирования утеряна. Открой карточку заново.")
        return
    try:
        updated = await update_uc(
            UpdateFandomCommand(actor_id=message.from_user.id, fandom_id=fid, aliases=aliases)
        )
    except DomainError as e:
        await message.answer(f"❌ {e}")
        return
    await state.clear()
    row = await repo.get(FandomId(int(updated.id)))
    if row is None:
        await message.answer("❌ Не найден после правки.")
        return
    cat_for_back = cat or row.category
    await message.answer(
        _format_card(row),
        reply_markup=build_admin_fandom_card_kb(
            fid=int(row.id), cat=cat_for_back, active=row.active
        ),
        parse_mode="HTML",
    )


# ============================================================
# Поиск (FSM)
# ============================================================


@router.callback_query(FdAdmCD.filter(F.a == "search"), IsAdmin())
async def start_search(
    cb: CallbackQuery,
    callback_data: FdAdmCD,
    state: FSMContext,
) -> None:
    await state.set_state(FandomSearchFlow.waiting_query)
    await state.update_data(cat=callback_data.cat)
    scope = (
        f"в категории <b>{escape(category_long_label(callback_data.cat))}</b>"
        if callback_data.cat
        else "по всем категориям"
    )
    await render(
        cb,
        f"🔍 <b>Поиск фандома</b>\n\nИщем {scope}.\n"
        "Пришли название (минимум 2 символа).\nВключаем неактивные.",
        reply_markup=build_admin_fandoms_back_kb(cat=callback_data.cat),
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(FandomSearchFlow.waiting_query, F.chat.type == "private", IsAdmin())
@inject
async def receive_search_query(
    message: Message,
    state: FSMContext,
    search_uc: FromDishka[SearchFandomsAdminUseCase],
) -> None:
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("❌ Минимум 2 символа. Пришли запрос ещё раз:")
        return
    data = await state.get_data()
    cat = str(data.get("cat") or "")
    items = await search_uc(query=query, limit=30, category=cat or None)
    await state.clear()
    if not items:
        scope = f"в «{category_short_label(cat)}»" if cat else "по всем категориям"
        body = f"🔍 <b>Поиск</b>: <code>{escape(query)}</code> {scope}\n\n<i>Ничего не найдено.</i>"
    else:
        body = f"🔍 <b>Найдено: {len(items)}</b>\nЗапрос: <code>{escape(query)}</code>"
    await message.answer(
        body,
        reply_markup=build_admin_search_results_kb(items=items, cat=cat),
        parse_mode="HTML",
    )


# ============================================================
# Создание нового фандома (FSM)
# ============================================================


@router.callback_query(FdAdmCD.filter(F.a == "new"), IsAdmin())
async def start_new_fandom(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FandomCreateFlow.waiting_category)
    await render(
        cb,
        "✏️ <b>Новый фандом</b> — шаг 1/3\n\nВыбери категорию:",
        reply_markup=build_admin_create_categories_kb(),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(FdAdmCD.filter(F.a == "new_in"), IsAdmin())
async def start_new_in_category(
    cb: CallbackQuery,
    callback_data: FdAdmCD,
    state: FSMContext,
) -> None:
    cat = callback_data.cat
    if not _ensure_known_category(cat):
        await cb.answer("Неизвестная категория.", show_alert=True)
        return
    await state.clear()
    await state.set_state(FandomCreateFlow.waiting_name)
    await state.update_data(category=cat)
    await render(
        cb,
        f"✏️ <b>Новый фандом в «{escape(category_long_label(cat))}»</b> — шаг 2/3\n\n"
        "Пришли название (1–256 символов):",
        reply_markup=build_admin_fandoms_back_kb(cat=cat),
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(FandomCreateFlow.waiting_name, F.chat.type == "private", IsAdmin())
async def receive_create_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 256:
        await message.answer("❌ Название должно быть от 1 до 256 символов. Пришли ещё раз:")
        return
    await state.update_data(name=name)
    await state.set_state(FandomCreateFlow.waiting_aliases)
    data = await state.get_data()
    cat = str(data.get("category") or "")
    await message.answer(
        "✏️ <b>Шаг 3/3</b> — альтернативные названия.\n\n"
        "Через запятую, например: <i>HP, Harry Potter, ГП</i>.\n"
        "Если не нужно — пришли «-».",
        reply_markup=build_admin_fandoms_back_kb(cat=cat),
        parse_mode="HTML",
    )


@router.message(FandomCreateFlow.waiting_aliases, F.chat.type == "private", IsAdmin())
@inject
async def receive_create_aliases(
    message: Message,
    state: FSMContext,
    create_uc: FromDishka[CreateFandomUseCase],
) -> None:
    if message.from_user is None:
        return
    raw = (message.text or "").strip()
    aliases = [] if raw in {"-", ""} else [x.strip() for x in raw.split(",") if x.strip()]
    data = await state.get_data()
    name = str(data.get("name") or "")
    category = str(data.get("category") or "")
    if not name or not category:
        await state.clear()
        await message.answer("❌ Сессия создания утеряна. Запусти заново через «➕ Новый фандом».")
        return
    try:
        row = await create_uc(
            CreateFandomCommand(
                actor_id=message.from_user.id,
                name=name,
                category=category,
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
        f"  категория: {escape(category_long_label(row.category))}\n"
        f"  alias'ов: {len(row.aliases)}",
        reply_markup=build_admin_fandom_card_kb(fid=int(row.id), cat=row.category, active=True),
        parse_mode="HTML",
    )


# NOOP callback ("noop") обрабатывается глобально в routers/reader.py.
