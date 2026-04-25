"""Роутер админа: управление UTM-трекинг кодами + воронка."""

from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.stats.get_funnel import (
    GetFunnelCommand,
    GetFunnelUseCase,
)
from app.application.tracking.create_code import (
    CreateTrackingCodeCommand,
    CreateTrackingCodeUseCase,
)
from app.application.tracking.deactivate_code import (
    DeactivateCodeCommand,
    DeactivateTrackingCodeUseCase,
)
from app.application.tracking.list_codes import ListTrackingCodesUseCase
from app.application.tracking.ports import ITrackingRepository
from app.application.users.export_user_ids import (
    ExportUtmUserIdsCommand,
    ExportUtmUserIdsUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.domain.shared.types import TrackingCodeId
from app.infrastructure.stats.charts import render_funnel_png
from app.presentation.bot.callback_data.admin import AdminCD, TrackingCD
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.fsm.states.admin_tracking import TrackingCodeFlow
from app.presentation.bot.keyboards.admin_tracking import (
    build_tracking_card_kb,
    build_tracking_funnel_back_kb,
    build_tracking_menu_kb,
)
from app.presentation.bot.ui_helpers import render, render_photo

log = get_logger(__name__)
router = Router(name="admin_tracking")


async def _show_tracking_list(
    *, event: CallbackQuery | Message, list_uc: ListTrackingCodesUseCase
) -> None:
    codes = await list_uc(active_only=False)
    items = [(int(c.id) if c.id else 0, str(c.code), str(c.name), bool(c.active)) for c in codes]
    header = "🔗 <b>Трекинговые ссылки</b>"
    if not items:
        text = header + "\n\nЕщё ни одного кода не создано."
    else:
        text = header + f"\n\nВсего: {len(items)}. Выбери для подробностей."
    await render(event, text, reply_markup=build_tracking_menu_kb(items), parse_mode="HTML")


@router.callback_query(AdminCD.filter(F.action == "tracking"), IsAdmin())
@router.callback_query(TrackingCD.filter(F.action == "list"), IsAdmin())
@inject
async def show_tracking(
    cb: CallbackQuery,
    list_uc: FromDishka[ListTrackingCodesUseCase],
) -> None:
    await _show_tracking_list(event=cb, list_uc=list_uc)
    await cb.answer()


# ---------- новый код ----------


@router.callback_query(TrackingCD.filter(F.action == "new"), IsAdmin())
async def new_code_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(TrackingCodeFlow.waiting_name)
    await render(
        cb,
        "✏️ Введи человеко-читаемое имя кампании (например: «Канал @examples» или «Реклама ВК»):",
    )
    await cb.answer()


@router.message(TrackingCodeFlow.waiting_name, F.chat.type == "private", IsAdmin())
async def receive_tracking_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 128:
        await message.answer("❌ Имя должно быть от 1 до 128 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(TrackingCodeFlow.waiting_description)
    await message.answer(
        "✏️ Описание (необязательно) — пришли текст или отправь «-», чтобы пропустить."
    )


@router.message(TrackingCodeFlow.waiting_description, F.chat.type == "private", IsAdmin())
@inject
async def receive_tracking_description(
    message: Message,
    state: FSMContext,
    bot: FromDishka[Bot],
    uc: FromDishka[CreateTrackingCodeUseCase],
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    name = str(data.get("name") or "")
    desc_raw = (message.text or "").strip()
    description = None if desc_raw == "-" else desc_raw or None

    try:
        result = await uc(
            CreateTrackingCodeCommand(
                created_by=message.from_user.id,
                name=name,
                description=description,
            )
        )
    except DomainError as e:
        await message.answer(f"❌ {e}")
        await state.clear()
        return

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={result.code}"
    await message.answer(
        f"✅ Трекинговая ссылка создана.\n\nКод: {result.code}\nСсылка для рекламы:\n{link}"
    )
    await state.clear()


# ---------- карточка кода ----------


@router.callback_query(TrackingCD.filter(F.action == "open"), IsAdmin())
@inject
async def open_tracking_card(
    cb: CallbackQuery,
    callback_data: TrackingCD,
    bot: FromDishka[Bot],
    tracking: FromDishka[ITrackingRepository],
    funnel_uc: FromDishka[GetFunnelUseCase],
) -> None:
    code = await tracking.get_code(TrackingCodeId(int(callback_data.code_id)))
    if code is None:
        await cb.answer("Код не найден.", show_alert=True)
        return
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={code.code}"

    # Сразу подтягиваем воронку — чтобы показать на карточке summary.
    try:
        funnel = await funnel_uc(GetFunnelCommand(code=str(code.code), days=30))
    except DomainError:
        funnel = None

    lines = [
        "🔗 <b>Трекинговая ссылка</b>",
        "",
        f"Код: <code>{escape(str(code.code))}</code>",
        f"Имя: {escape(str(code.name))}",
        f"Описание: {escape(code.description) if code.description else '—'}",
        f"Статус: {'активна' if code.active else 'выключена'}",
        "",
        f"Ссылка:\n{escape(link)}",
    ]
    if funnel is not None:
        lines.extend(
            [
                "",
                "<b>📊 Статистика за 30 дней</b>",
                f"  👤 Новых пользователей: {funnel.transitions}",
                f"  📖 Начали читать:       {funnel.first_reads}",
                f"  ✍️ Опубликовали:        {funnel.first_publishes}",
                f"  🚫 Заблокировали бота:  {funnel.blocked_bot}",
            ]
        )

    await render(
        cb,
        "\n".join(lines),
        reply_markup=build_tracking_card_kb(int(code.id) if code.id else 0, active=code.active),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(TrackingCD.filter(F.action == "funnel"), IsAdmin())
@inject
async def show_funnel(
    cb: CallbackQuery,
    callback_data: TrackingCD,
    tracking: FromDishka[ITrackingRepository],
    funnel_uc: FromDishka[GetFunnelUseCase],
) -> None:
    code = await tracking.get_code(TrackingCodeId(int(callback_data.code_id)))
    if code is None:
        await cb.answer("Код не найден.", show_alert=True)
        return
    try:
        row = await funnel_uc(GetFunnelCommand(code=str(code.code), days=30))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return

    text = (
        f"📊 <b>Воронка за 30 дней</b>\n"
        f"Код: <code>{escape(str(row.code))}</code> — {escape(str(row.name))}\n\n"
        f"👤 Новых пользователей:  {row.transitions}\n"
        f"📖 Начали читать:        {row.first_reads}\n"
        f"✍️ Опубликовали:         {row.first_publishes}\n"
        f"🚫 Заблокировали бота:   {row.blocked_bot}"
    )
    png = render_funnel_png(row)
    await render_photo(
        cb,
        photo=BufferedInputFile(png, f"funnel_{row.code}.png"),
        caption=text,
        reply_markup=build_tracking_funnel_back_kb(int(callback_data.code_id)),
    )
    await cb.answer()


@router.callback_query(TrackingCD.filter(F.action == "export_users"), IsAdmin())
@inject
async def export_utm_users(
    cb: CallbackQuery,
    callback_data: TrackingCD,
    uc: FromDishka[ExportUtmUserIdsUseCase],
) -> None:
    """Выгрузить .txt с id юзеров, пришедших по этой UTM-ссылке (first-touch)."""
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await uc(
            ExportUtmUserIdsCommand(
                actor_id=cb.from_user.id,
                code_id=int(callback_data.code_id),
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    if not result.user_ids:
        await cb.answer("По этой ссылке ещё никто не пришёл.", show_alert=True)
        return
    # Файл строго: id в столбик, без BOM/заголовков. Trailing \n — стандартно.
    body = "\n".join(str(uid) for uid in result.user_ids) + "\n"
    document = BufferedInputFile(body.encode("utf-8"), filename=f"{result.label}.txt")
    await cb.message.answer_document(
        document=document,
        caption=f"📥 Выгрузка по {escape(result.label)}: <b>{len(result.user_ids)}</b> id.",
        parse_mode="HTML",
    )
    await cb.answer(f"Готово: {len(result.user_ids)} id")


@router.callback_query(TrackingCD.filter(F.action == "deactivate"), IsAdmin())
@inject
async def deactivate_code(
    cb: CallbackQuery,
    callback_data: TrackingCD,
    uc: FromDishka[DeactivateTrackingCodeUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()  # type: ignore[unreachable]
        return
    try:
        await uc(DeactivateCodeCommand(code_id=callback_data.code_id, actor_id=cb.from_user.id))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("🔒 Трекинговая ссылка выключена.")
    # Перерисуем карточку — статус обновится.
    await render(cb, "🔒 Трекинговая ссылка выключена.")
