"""Хелперы для буфера длинной главы в FSM.

Telegram ограничивает одно сообщение 4096 UTF-16 units, а лимит главы — 100_000.
Собираем главу из нескольких присланных сообщений; хранимся в FSM data.

Поля FSM:
- chapter_text_buf: str
- chapter_entities_buf: list[dict]
- chapter_u16_buf: int  (длина chapter_text_buf в UTF-16 units)
"""

from __future__ import annotations

from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.domain.shared.utf16 import utf16_length

SEP = "\n\n"
SEP_U16 = utf16_length(SEP)


def build_chapter_compose_kb(*, u16: int, limit: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=f"✅ Закончить главу ({u16}/{limit})",
        callback_data="chapter:finish",
    )
    b.button(text="⛔ Отмена", callback_data="chapter:cancel")
    b.adjust(1)
    return b.as_markup()


def dump_entities(entities: Any) -> list[dict[str, Any]]:
    if not entities:
        return []
    out: list[dict[str, Any]] = []
    for e in entities:
        try:
            out.append(e.model_dump(exclude_none=True))
        except AttributeError:
            if isinstance(e, dict):
                out.append(e)
    return out


async def append_chunk(
    state: FSMContext,
    message: Message,
    *,
    max_chars: int,
) -> tuple[int, bool]:
    """Добавить текст очередного сообщения к буферу главы.

    Returns:
        (new_u16_total, overflow): overflow=True если сегмент выталкивает нас за лимит —
        в этом случае буфер НЕ меняется, хендлер должен показать ошибку.
    """
    data = await state.get_data()
    buf: str = str(data.get("chapter_text_buf") or "")
    entities_buf: list[dict[str, Any]] = list(data.get("chapter_entities_buf") or [])
    u16_buf: int = int(data.get("chapter_u16_buf") or 0)

    text_new = message.text or ""
    ents_new = dump_entities(message.entities)
    new_u16 = utf16_length(text_new)

    if buf:
        shift = u16_buf + SEP_U16
        shifted = [{**e, "offset": int(e["offset"]) + shift} for e in ents_new]
        projected_u16 = u16_buf + SEP_U16 + new_u16
        if projected_u16 > max_chars:
            return projected_u16, True
        buf = buf + SEP + text_new
        entities_buf = entities_buf + shifted
    else:
        if new_u16 > max_chars:
            return new_u16, True
        buf = text_new
        entities_buf = ents_new

    u16_buf = utf16_length(buf)
    await state.update_data(
        chapter_text_buf=buf,
        chapter_entities_buf=entities_buf,
        chapter_u16_buf=u16_buf,
    )
    return u16_buf, False


async def read_buffer(
    state: FSMContext,
) -> tuple[str, list[dict[str, Any]], int]:
    data = await state.get_data()
    return (
        str(data.get("chapter_text_buf") or ""),
        list(data.get("chapter_entities_buf") or []),
        int(data.get("chapter_u16_buf") or 0),
    )


async def reset_buffer(state: FSMContext) -> None:
    await state.update_data(
        chapter_text_buf="",
        chapter_entities_buf=[],
        chapter_u16_buf=0,
    )
