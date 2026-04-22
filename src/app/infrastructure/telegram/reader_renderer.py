"""Формирование Telegram-сообщений читалки: префикс + текст страницы + entities.

Формат из docs/09-reader-pagination.md:

    <b>Глава 3 · «Тишина»</b>
    <i>Страница 2 из 8</i>
    <пустая строка>
    <текст страницы>

Префикс — это bold-заголовок и italic-строка со сдвигом offsets для
entities страницы.
"""

from __future__ import annotations

from typing import Any

from app.domain.fanfics.entities import Chapter, Fanfic
from app.domain.fanfics.services.paginator import Page, shift_entities
from app.domain.shared.utf16 import utf16_length


def build_reader_message(
    *,
    fic: Fanfic,
    chapter: Chapter,
    page: Page,
    total_pages: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Вернуть (text, entities) для send_message / edit_message_text."""
    title_line = f"Глава {int(chapter.number)} · «{chapter.title}»"
    page_line = f"Страница {page.page_no} из {total_pages}"
    prefix = f"{title_line}\n{page_line}\n\n"
    prefix_u16 = utf16_length(prefix)

    prefix_entities: list[dict[str, Any]] = [
        {"type": "bold", "offset": 0, "length": utf16_length(title_line)},
        {
            "type": "italic",
            "offset": utf16_length(title_line) + 1,  # +1 за "\n"
            "length": utf16_length(page_line),
        },
    ]

    shifted = shift_entities(list(page.entities or []), prefix_u16)
    return prefix + page.text, prefix_entities + shifted


def build_cover_caption(fic: Fanfic, author_nick: str | None) -> tuple[str, list[dict[str, Any]]]:
    """Caption для send_photo (обложка)."""
    title = str(fic.title)
    by = f" · {author_nick}" if author_nick else ""
    header = f"{title}{by}\n\n"
    header_u16 = utf16_length(header)

    # bold на title
    entities: list[dict[str, Any]] = [
        {"type": "bold", "offset": 0, "length": utf16_length(title)},
    ]
    # summary как хвост caption
    body = str(fic.summary)
    text = header + body
    summary_entities = shift_entities(list(fic.summary_entities or []), header_u16)
    return text, entities + summary_entities
