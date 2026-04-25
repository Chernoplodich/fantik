"""Клавиатуры wizard создания рассылки + карточка существующей."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.admin import (
    AdminCD,
    BroadcastCD,
    ConfirmCD,
    KeyboardChoiceCD,
    ScheduleCD,
    SegmentCD,
)


def build_keyboard_choice_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить кнопки", callback_data=KeyboardChoiceCD(choice="yes").pack())
    b.button(text="⏭ Без кнопок", callback_data=KeyboardChoiceCD(choice="no").pack())
    b.adjust(2)
    return b.as_markup()


def build_segment_presets_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="👥 Все пользователи", callback_data=SegmentCD(kind="all").pack())
    b.button(text="✍️ Только авторы", callback_data=SegmentCD(kind="authors").pack())
    b.button(text="◀︎ Отмена", callback_data=AdminCD(action="broadcasts").pack())
    b.adjust(1)
    return b.as_markup()


def build_schedule_choice_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🚀 Сразу", callback_data=ScheduleCD(kind="now").pack())
    b.button(text="📅 Отложить", callback_data=ScheduleCD(kind="schedule").pack())
    b.button(text="◀︎ Отмена", callback_data=ScheduleCD(kind="cancel").pack())
    b.adjust(2, 1)
    return b.as_markup()


def build_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Запустить", callback_data=ConfirmCD(action="ok").pack())
    b.button(text="◀︎ Отмена", callback_data=ConfirmCD(action="cancel").pack())
    b.adjust(2)
    return b.as_markup()


def build_broadcast_card_kb(
    *,
    broadcast_id: int,
    can_cancel: bool,
    can_retry_failed: bool,
    show_refresh: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if show_refresh:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=BroadcastCD(action="refresh", bid=broadcast_id).pack(),
                )
            ]
        )
    if can_cancel:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛑 Отменить",
                    callback_data=BroadcastCD(action="cancel", bid=broadcast_id).pack(),
                )
            ]
        )
    if can_retry_failed:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Повторить для упавших",
                    callback_data=BroadcastCD(action="retry_failed", bid=broadcast_id).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="📣 К списку рассылок",
                callback_data=BroadcastCD(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_broadcast_list_kb(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """items: list[(broadcast_id, short_label)]."""
    b = InlineKeyboardBuilder()
    for bid, label in items:
        b.button(text=label, callback_data=BroadcastCD(action="open", bid=bid).pack())
    b.button(text="➕ Новая рассылка", callback_data=BroadcastCD(action="new").pack())
    b.button(text="◀︎ Админ-меню", callback_data=AdminCD(action="root").pack())
    b.adjust(1)
    return b.as_markup()


def build_after_launch_kb(broadcast_id: int) -> InlineKeyboardMarkup:
    """После успешного запуска/планирования — навигация обратно."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👁 Открыть карточку",
                    callback_data=BroadcastCD(action="open", bid=broadcast_id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📣 К рассылкам",
                    callback_data=BroadcastCD(action="list").pack(),
                ),
                InlineKeyboardButton(
                    text="⚙️ Админ-меню",
                    callback_data=AdminCD(action="root").pack(),
                ),
            ],
        ]
    )
