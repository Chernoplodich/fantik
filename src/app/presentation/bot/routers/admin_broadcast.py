"""Роутер создания/управления рассылками (admin only)."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.broadcasts.cancel import (
    CancelBroadcastCommand,
    CancelBroadcastUseCase,
)
from app.application.broadcasts.create_draft import (
    CreateBroadcastDraftCommand,
    CreateBroadcastDraftUseCase,
)
from app.application.broadcasts.launch import (
    LaunchBroadcastCommand,
    LaunchBroadcastUseCase,
)
from app.application.broadcasts.list_broadcasts import (
    GetBroadcastCardUseCase,
    ListMyBroadcastsUseCase,
)
from app.application.broadcasts.schedule import (
    ScheduleBroadcastCommand,
    ScheduleBroadcastUseCase,
)
from app.application.broadcasts.set_keyboard import (
    SetKeyboardCommand,
    SetKeyboardUseCase,
)
from app.application.broadcasts.set_segment import (
    SetSegmentCommand,
    SetSegmentUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.domain.broadcasts.segment import describe_segment
from app.domain.broadcasts.value_objects import (
    FINAL_STATUSES,
    BroadcastStatus,
    DeliveryStatus,
)
from app.presentation.bot.callback_data.admin import (
    AdminCD,
    BroadcastCD,
    ConfirmCD,
    KeyboardChoiceCD,
    ScheduleCD,
    SegmentCD,
)
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.fsm.states.broadcast import BroadcastFlow
from app.presentation.bot.keyboards.broadcast_wizard import (
    build_after_launch_kb,
    build_broadcast_card_kb,
    build_broadcast_list_kb,
    build_confirm_kb,
    build_keyboard_choice_kb,
    build_schedule_choice_kb,
    build_segment_presets_kb,
)
from app.presentation.bot.ui_helpers import render as _ui_render

log = get_logger(__name__)
router = Router(name="admin_broadcast")


# ---------- helpers ----------


_BC_STATUS_RU = {
    "draft": "черновик",
    "scheduled": "запланирована",
    "running": "идёт",
    "finished": "завершена",
    "cancelled": "отменена",
    "failed": "ошибка",
}


async def _show_broadcasts_list(
    *,
    event: CallbackQuery | Message,
    list_uc: ListMyBroadcastsUseCase,
    user_id: int,
) -> None:
    items = await list_uc(created_by=user_id, limit=20)
    labels: list[tuple[int, str]] = []
    for bc in items:
        created = bc.created_at.strftime("%d.%m %H:%M") if bc.created_at else "—"
        status_ru = _BC_STATUS_RU.get(bc.status.value, bc.status.value)
        labels.append(
            (
                int(bc.id),
                f"#{int(bc.id)} · {status_ru} · {created}",
            )
        )
    text = "📣 <b>Рассылки</b>\n\nВыбери рассылку или создай новую."
    await _ui_render(event, text, reply_markup=build_broadcast_list_kb(labels), parse_mode="HTML")


# ---------- entry ----------


@router.message(Command("broadcast"), IsAdmin())
@inject
async def cmd_broadcast(
    message: Message,
    state: FSMContext,
    list_uc: FromDishka[ListMyBroadcastsUseCase],
) -> None:
    if message.from_user is None:
        return
    await state.clear()
    await _show_broadcasts_list(event=message, list_uc=list_uc, user_id=message.from_user.id)


@router.callback_query(AdminCD.filter(F.action == "broadcasts"), IsAdmin())
@inject
async def open_broadcasts_menu(
    cb: CallbackQuery,
    state: FSMContext,
    list_uc: FromDishka[ListMyBroadcastsUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    await state.clear()
    await _show_broadcasts_list(event=cb, list_uc=list_uc, user_id=cb.from_user.id)
    await cb.answer()


@router.callback_query(BroadcastCD.filter(F.action == "list"), IsAdmin())
@inject
async def show_list(
    cb: CallbackQuery,
    state: FSMContext,
    list_uc: FromDishka[ListMyBroadcastsUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    await state.clear()
    await _show_broadcasts_list(event=cb, list_uc=list_uc, user_id=cb.from_user.id)
    await cb.answer()


# ---------- new broadcast: шаблон ----------


@router.callback_query(BroadcastCD.filter(F.action == "new"), IsAdmin())
async def start_new_broadcast(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BroadcastFlow.waiting_source)
    await _ui_render(
        cb,
        "📝 Отправь (или перешли сюда) сообщение-шаблон рассылки.\n\n"
        "Поддерживаются: текст, фото с подписью, custom emoji, inline-форматирование. "
        "Медиа-группы и сервисные сообщения не поддерживаются.",
    )
    await cb.answer()


@router.message(BroadcastFlow.waiting_source, F.chat.type == "private", IsAdmin())
@inject
async def on_source_message(
    message: Message,
    state: FSMContext,
    bot: FromDishka[Bot],
    uc: FromDishka[CreateBroadcastDraftUseCase],
    set_kb_uc: FromDishka[SetKeyboardUseCase],
) -> None:
    if message.from_user is None:
        return
    # Не принимаем сервисные/неподдерживаемые типы.
    if message.media_group_id is not None:
        await message.answer("❌ Медиа-группы пока не поддерживаются. Отправь одиночное сообщение.")
        return

    try:
        result = await uc(
            CreateBroadcastDraftCommand(
                created_by=message.from_user.id,
                source_chat_id=message.chat.id,
                source_message_id=message.message_id,
            )
        )
    except DomainError as e:
        await message.answer(f"❌ {e}")
        await state.clear()
        return

    await state.update_data(broadcast_id=result.broadcast_id)

    # Если у forwarded сообщения есть inline-клавиатура (переслано с бот-поста,
    # где TG её сохранил), подхватываем её автоматически — админу не надо
    # ничего вводить.
    captured_kb = _extract_inline_keyboard(message.reply_markup)

    # Превью: бот копирует шаблон туда же — админ видит, как это будет у читателя.
    # copy_message не переносит inline-кнопки; если мы захватили их —
    # прикрепляем, чтобы превью совпало с тем, что увидят получатели.
    try:
        preview_markup = (
            InlineKeyboardMarkup(inline_keyboard=message.reply_markup.inline_keyboard)
            if (
                message.reply_markup is not None
                and isinstance(message.reply_markup, InlineKeyboardMarkup)
                and captured_kb
            )
            else None
        )
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=preview_markup,
        )
    except TelegramBadRequest as e:
        log.warning("broadcast_preview_copy_failed", error=str(e))

    if captured_kb is not None:
        try:
            await set_kb_uc(
                SetKeyboardCommand(broadcast_id=result.broadcast_id, keyboard=captured_kb)
            )
        except DomainError as e:
            log.warning("broadcast_captured_kb_save_failed", error=str(e))
        await message.answer(
            f"✅ Шаблон принят вместе с клавиатурой "
            f"({sum(len(r) for r in captured_kb)} кнопок в "
            f"{len(captured_kb)} ряду(ях)).\n\n"
            "Выбери сегмент получателей:",
            reply_markup=build_segment_presets_kb(),
        )
        await state.set_state(BroadcastFlow.waiting_segment)
    else:
        await message.answer(
            "✅ Шаблон принят. Добавить inline-кнопки?",
            reply_markup=build_keyboard_choice_kb(),
        )
        await state.set_state(BroadcastFlow.waiting_keyboard_choice)


def _extract_inline_keyboard(
    reply_markup: object | None,
) -> list[list[dict[str, Any]]] | None:
    """Попытаться достать InlineKeyboardMarkup → list[list[dict]].

    Возвращает структуру, совместимую с broadcast.keyboard (jsonb).
    None — если reply_markup отсутствует / это не inline, или кнопок нет.
    """
    if reply_markup is None:
        return None
    if not isinstance(reply_markup, InlineKeyboardMarkup):
        return None
    rows: list[list[dict[str, Any]]] = []
    for row in reply_markup.inline_keyboard or []:
        row_out: list[dict[str, Any]] = []
        for btn in row:
            # Сохраняем только кнопки с url или callback_data — остальные
            # (WebApp, login_url, pay и т.п.) не воспроизведутся корректно в
            # broадкасте без ручной настройки.
            data = btn.model_dump(exclude_none=True)
            safe = {"text": data.get("text", "")}
            if "url" in data:
                safe["url"] = data["url"]
            elif "callback_data" in data:
                safe["callback_data"] = data["callback_data"]
            elif "switch_inline_query" in data:
                safe["switch_inline_query"] = data["switch_inline_query"]
            elif "switch_inline_query_current_chat" in data:
                safe["switch_inline_query_current_chat"] = data["switch_inline_query_current_chat"]
            else:
                # Кнопка без поддерживаемого действия — пропускаем.
                continue
            row_out.append(safe)
        if row_out:
            rows.append(row_out)
    return rows or None


# ---------- wizard: клавиатура ----------


@router.callback_query(
    KeyboardChoiceCD.filter(F.choice == "no"),
    BroadcastFlow.waiting_keyboard_choice,
    IsAdmin(),
)
async def skip_keyboard(cb: CallbackQuery, state: FSMContext) -> None:
    await _ui_render(
        cb,
        "👥 Выбери сегмент получателей:",
        reply_markup=build_segment_presets_kb(),
    )
    await state.set_state(BroadcastFlow.waiting_segment)
    await cb.answer()


@router.callback_query(
    KeyboardChoiceCD.filter(F.choice == "yes"),
    BroadcastFlow.waiting_keyboard_choice,
    IsAdmin(),
)
async def ask_keyboard_input(cb: CallbackQuery, state: FSMContext) -> None:
    await _ui_render(
        cb,
        "✏️ Введи строки кнопок в формате:\n\n"
        "Текст кнопки|https://url\n"
        "Ещё одна|tg://resolve?domain=example\n\n"
        "Пустая строка — новый ряд в клавиатуре. Отправь одним сообщением.",
    )
    await state.set_state(BroadcastFlow.waiting_keyboard_input)
    await cb.answer()


@router.message(BroadcastFlow.waiting_keyboard_input, F.chat.type == "private", IsAdmin())
@inject
async def receive_keyboard_input(
    message: Message,
    state: FSMContext,
    uc: FromDishka[SetKeyboardUseCase],
) -> None:
    data = await state.get_data()
    bid = int(data.get("broadcast_id", 0))
    raw = (message.text or message.caption or "").strip()
    if not raw:
        await message.answer("❌ Пустое сообщение. Пришли строки кнопок.")
        return
    try:
        await uc(SetKeyboardCommand(broadcast_id=bid, raw_text=raw))
    except DomainError as e:
        await message.answer(f"❌ {e}\nПопробуй снова.")
        return
    await message.answer(
        "✅ Клавиатура сохранена. Выбери сегмент получателей:",
        reply_markup=build_segment_presets_kb(),
    )
    await state.set_state(BroadcastFlow.waiting_segment)


# ---------- wizard: сегмент ----------


@router.callback_query(SegmentCD.filter(F.kind == "all"), BroadcastFlow.waiting_segment, IsAdmin())
@inject
async def segment_all(
    cb: CallbackQuery,
    state: FSMContext,
    uc: FromDishka[SetSegmentUseCase],
) -> None:
    await _apply_segment_and_ask_schedule(cb, state, uc, {"kind": "all"})


@router.callback_query(
    SegmentCD.filter(F.kind == "authors"), BroadcastFlow.waiting_segment, IsAdmin()
)
@inject
async def segment_authors(
    cb: CallbackQuery,
    state: FSMContext,
    uc: FromDishka[SetSegmentUseCase],
) -> None:
    await _apply_segment_and_ask_schedule(cb, state, uc, {"kind": "authors"})


async def _apply_segment_and_ask_schedule(
    cb: CallbackQuery,
    state: FSMContext,
    uc: SetSegmentUseCase,
    spec: dict[str, Any],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    data = await state.get_data()
    bid = int(data.get("broadcast_id", 0))
    try:
        await uc(SetSegmentCommand(broadcast_id=bid, spec=spec))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await _ui_render(
        cb,
        f"✅ Сегмент: {describe_segment(spec)}\n\nКогда запустить?",
        reply_markup=build_schedule_choice_kb(),
    )
    await state.set_state(BroadcastFlow.waiting_schedule_choice)
    await cb.answer()


# ---------- wizard: расписание ----------


@router.callback_query(
    ScheduleCD.filter(F.kind == "now"),
    BroadcastFlow.waiting_schedule_choice,
    IsAdmin(),
)
async def schedule_now(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(schedule_mode="now")
    await _ui_render(
        cb,
        "🚀 Запустить рассылку сразу?",
        reply_markup=build_confirm_kb(),
    )
    await state.set_state(BroadcastFlow.confirm)
    await cb.answer()


@router.callback_query(
    ScheduleCD.filter(F.kind == "schedule"),
    BroadcastFlow.waiting_schedule_choice,
    IsAdmin(),
)
async def schedule_later_ask(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await _ui_render(
        cb,
        "📅 Пришли дату и время запуска в формате:\n\n"
        "  <b>ДД.ММ.ГГГГ ЧЧ:ММ</b>\n\n"
        "Например: 10.10.2026 10:10\n\n"
        "Время по московскому часовому поясу (МСК, UTC+3).",
        parse_mode="HTML",
    )
    await state.set_state(BroadcastFlow.waiting_schedule_datetime)
    await cb.answer()


@router.callback_query(
    ScheduleCD.filter(F.kind == "cancel"),
    BroadcastFlow.waiting_schedule_choice,
    IsAdmin(),
)
async def schedule_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _ui_render(
        cb,
        "Создание рассылки отменено. Черновик сохранён — можно продолжить позже.",
    )
    await cb.answer()


@router.message(BroadcastFlow.waiting_schedule_datetime, F.chat.type == "private", IsAdmin())
async def schedule_datetime(
    message: Message,
    state: FSMContext,
) -> None:
    raw = (message.text or "").strip()
    try:
        dt = datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Нужно: <b>ДД.ММ.ГГГГ ЧЧ:ММ</b>\nНапример: 10.10.2026 10:10",
            parse_mode="HTML",
        )
        return

    tz_msk = ZoneInfo("Europe/Moscow")
    dt_msk = dt.replace(tzinfo=tz_msk)
    now_msk = datetime.now(tz=tz_msk)

    if dt_msk <= now_msk:
        await message.answer(
            f"❌ Дата {dt_msk.strftime('%d.%m.%Y %H:%M')} МСК уже в прошлом.\n"
            f"Сейчас: {now_msk.strftime('%d.%m.%Y %H:%M')} МСК.\n"
            "Пришли дату в будущем."
        )
        return

    await state.update_data(
        schedule_mode="schedule",
        scheduled_at_iso=dt_msk.isoformat(),
    )
    delta = dt_msk - now_msk
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    delta_str = f"через {hours}ч {minutes}мин" if hours else f"через {minutes}мин"

    await message.answer(
        f"📅 Рассылка будет запущена:\n\n"
        f"  <b>{dt_msk.strftime('%d.%m.%Y в %H:%M')} МСК</b>\n"
        f"  ({delta_str})\n\n"
        "Подтвердить?",
        parse_mode="HTML",
        reply_markup=build_confirm_kb(),
    )
    await state.set_state(BroadcastFlow.confirm)


# ---------- confirm ----------


@router.callback_query(ConfirmCD.filter(F.action == "ok"), BroadcastFlow.confirm, IsAdmin())
@inject
async def confirm_ok(
    cb: CallbackQuery,
    state: FSMContext,
    launch_uc: FromDishka[LaunchBroadcastUseCase],
    schedule_uc: FromDishka[ScheduleBroadcastUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    data = await state.get_data()
    bid = int(data.get("broadcast_id", 0))
    mode = data.get("schedule_mode")
    try:
        if mode == "now":
            await launch_uc(LaunchBroadcastCommand(broadcast_id=bid, actor_id=cb.from_user.id))
            await _ui_render(
                cb,
                f"🚀 Рассылка #{bid} запущена.\nПрогресс можно отслеживать в карточке рассылки.",
                reply_markup=build_after_launch_kb(bid),
            )
        elif mode == "schedule":
            scheduled_at = datetime.fromisoformat(str(data.get("scheduled_at_iso")))
            await schedule_uc(
                ScheduleBroadcastCommand(
                    broadcast_id=bid,
                    actor_id=cb.from_user.id,
                    scheduled_at=scheduled_at,
                )
            )
            msk = scheduled_at.astimezone(ZoneInfo("Europe/Moscow"))
            await _ui_render(
                cb,
                f"📅 Рассылка #{bid} запланирована на {msk.strftime('%d.%m.%Y %H:%M')} МСК.",
                reply_markup=build_after_launch_kb(bid),
            )
        else:
            await _ui_render(cb, "❌ Неизвестный режим запуска.")
    except DomainError as e:
        await _ui_render(cb, f"❌ {e}")
    await state.clear()
    await cb.answer()


@router.callback_query(ConfirmCD.filter(F.action == "cancel"), BroadcastFlow.confirm, IsAdmin())
async def confirm_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _ui_render(cb, "Запуск отменён. Черновик сохранён.")
    await cb.answer()


# ---------- карточка рассылки ----------


@router.callback_query(BroadcastCD.filter(F.action == "open"), IsAdmin())
@router.callback_query(BroadcastCD.filter(F.action == "refresh"), IsAdmin())
@inject
async def open_broadcast_card(
    cb: CallbackQuery,
    callback_data: BroadcastCD,
    card_uc: FromDishka[GetBroadcastCardUseCase],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    try:
        view = await card_uc(callback_data.bid)
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return

    text = _format_broadcast_card(view)
    bc = view.broadcast
    counts = view.counts

    can_cancel = bc.status not in FINAL_STATUSES
    can_retry_failed = (
        bc.status == BroadcastStatus.FINISHED and int(counts.get(DeliveryStatus.FAILED, 0)) > 0
    )
    show_refresh = bc.status in (BroadcastStatus.RUNNING, BroadcastStatus.SCHEDULED)

    kb = build_broadcast_card_kb(
        broadcast_id=int(bc.id),
        can_cancel=can_cancel,
        can_retry_failed=can_retry_failed,
        show_refresh=show_refresh,
    )
    await _ui_render(cb, text, reply_markup=kb, parse_mode="HTML")
    await cb.answer("Обновлено" if callback_data.action == "refresh" else None)


def _format_broadcast_card(view) -> str:  # type: ignore[no-untyped-def]
    """Рендер карточки рассылки: статус, сегмент, шкала прогресса, счётчики."""
    bc = view.broadcast
    counts = view.counts
    pending = int(counts.get(DeliveryStatus.PENDING, 0))
    sent = int(counts.get(DeliveryStatus.SENT, 0))
    failed = int(counts.get(DeliveryStatus.FAILED, 0))
    blocked = int(counts.get(DeliveryStatus.BLOCKED, 0))
    total_known = sent + failed + blocked + pending
    progress_done = sent + failed + blocked
    msk = ZoneInfo("Europe/Moscow")

    def _fmt(dt: datetime | None) -> str:
        if dt is None:
            return "—"
        return dt.astimezone(msk).strftime("%d.%m.%Y %H:%M") + " МСК"

    status_ru = _BC_STATUS_RU.get(bc.status.value, bc.status.value)
    lines = [
        f"📣 <b>Рассылка #{int(bc.id)}</b>",
        f"Статус: {escape(status_ru)}",
        f"Сегмент: {escape(describe_segment(bc.segment_spec))}",
        f"Клавиатура: {_describe_keyboard(bc.keyboard)}",
        f"Создана: {_fmt(bc.created_at)}",
    ]
    if bc.scheduled_at:
        lines.append(f"Запланирована: {_fmt(bc.scheduled_at)}")
    if bc.started_at:
        lines.append(f"Запущена: {_fmt(bc.started_at)}")
    if bc.finished_at:
        lines.append(f"Завершена: {_fmt(bc.finished_at)}")
    lines.append("")

    if total_known > 0:
        ratio = progress_done / total_known
        bar = _progress_bar(ratio)
        lines.append(f"{bar} {progress_done}/{total_known} ({ratio * 100:.1f}%)")
    else:
        lines.append("(получатели ещё не посчитаны)")

    lines.append("")
    lines.append(f"✅ Отправлено:          {sent}")
    lines.append(f"🚫 Заблокировали бота: {blocked}")
    lines.append(f"⚠️ Ошибки:             {failed}")
    if pending > 0:
        lines.append(f"⏳ В очереди:          {pending}")

    if bc.status == BroadcastStatus.FINISHED and bc.stats:
        total_stats = bc.stats.get("total", 0)
        lines.append("")
        lines.append(
            f"Итого: всего {total_stats}, отправлено {bc.stats.get('sent', 0)}, "
            f"ошибки {bc.stats.get('failed', 0)}, "
            f"заблокировали {bc.stats.get('blocked', 0)}"
        )

    return "\n".join(lines)


def _describe_keyboard(keyboard) -> str:  # type: ignore[no-untyped-def]
    if not keyboard:
        return "нет"
    buttons = sum(len(row) for row in keyboard)
    word_row = "ряду" if len(keyboard) == 1 else "рядах"
    return f"{buttons} кнопок в {len(keyboard)} {word_row}"


def _progress_bar(ratio: float, width: int = 20) -> str:
    """ASCII progress bar: ▓▓▓▓▓▓░░░░."""
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    return "▓" * filled + "░" * (width - filled)


@router.callback_query(BroadcastCD.filter(F.action == "cancel"), IsAdmin())
@inject
async def cancel_broadcast(
    cb: CallbackQuery,
    callback_data: BroadcastCD,
    uc: FromDishka[CancelBroadcastUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        await uc(CancelBroadcastCommand(broadcast_id=callback_data.bid, actor_id=cb.from_user.id))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("🛑 Рассылка отменена.")
    await _ui_render(cb, f"🛑 Рассылка #{callback_data.bid} отменена.")


@router.callback_query(BroadcastCD.filter(F.action == "retry_failed"), IsAdmin())
@inject
async def retry_failed(
    cb: CallbackQuery,
    callback_data: BroadcastCD,
    state: FSMContext,
    create_uc: FromDishka[CreateBroadcastDraftUseCase],
    set_seg_uc: FromDishka[SetSegmentUseCase],
    launch_uc: FromDishka[LaunchBroadcastUseCase],
    card_uc: FromDishka[GetBroadcastCardUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    # Создаём новую рассылку с тем же шаблоном и сегментом retry_failed.
    parent_view = await card_uc(callback_data.bid)
    parent = parent_view.broadcast
    try:
        new = await create_uc(
            CreateBroadcastDraftCommand(
                created_by=cb.from_user.id,
                source_chat_id=parent.source_chat_id,
                source_message_id=parent.source_message_id,
            )
        )
        await set_seg_uc(
            SetSegmentCommand(
                broadcast_id=new.broadcast_id,
                spec={"kind": "retry_failed", "parent_broadcast_id": callback_data.bid},
            )
        )
        await launch_uc(
            LaunchBroadcastCommand(broadcast_id=new.broadcast_id, actor_id=cb.from_user.id)
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("🔁 Повтор запущен")
    await _ui_render(
        cb,
        f"🔁 Повторная рассылка #{new.broadcast_id} запущена "
        f"для упавших получателей рассылки #{callback_data.bid}.",
    )
