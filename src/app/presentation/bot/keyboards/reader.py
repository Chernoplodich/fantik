"""Клавиатуры читалки."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.reading.ports import FeedItem
from app.domain.fanfics.entities import Chapter
from app.presentation.bot.callback_data.reader import ReadNav
from app.presentation.bot.keyboards.social import (
    report_fic_button,
    subscribe_button,
)

_NOOP = "noop"


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def cover_kb(
    *,
    fic_id: int,
    has_progress: bool,
    progress_chapter_no: int | None,
    progress_page_no: int | None,
    is_subscribed: bool = False,
    show_subscribe: bool = True,
) -> InlineKeyboardMarkup:
    """Клавиатура на карточке-обложке.

    Все кнопки чтения используют `a="read"`, т.к. cover — photo message:
    navigation через `edit_message_text` не работает. Handler `start_reading`
    удаляет сообщение-обложку и отправляет новое текстовое со страницей.

    `show_subscribe=False` используется, когда автор смотрит свою собственную
    работу (подписываться на себя нельзя).
    """
    b = InlineKeyboardBuilder()
    if has_progress and progress_chapter_no and progress_page_no:
        b.row(
            _btn(
                f"▶ Продолжить (гл.{progress_chapter_no}, стр.{progress_page_no})",
                ReadNav(a="read", f=fic_id, c=progress_chapter_no, p=progress_page_no).pack(),
            )
        )
        b.row(
            _btn(
                "📖 С начала",
                ReadNav(a="read", f=fic_id, c=1, p=1).pack(),
            )
        )
    else:
        b.row(
            _btn(
                "📖 Читать",
                ReadNav(a="read", f=fic_id, c=1, p=1).pack(),
            )
        )
    if show_subscribe:
        b.row(subscribe_button(fic_id=fic_id, is_subscribed=is_subscribed))
    b.row(report_fic_button(fic_id))
    b.row(_btn("⟵ Каталог", "menu:browse"))
    return b.as_markup()


def reader_kb(
    *,
    fic_id: int,
    chapter_no: int,
    page_no: int,
    total_pages: int,
    total_chapters: int,
    is_bookmarked: bool,
    is_liked: bool,
    is_last_page_in_chapter: bool,
    is_last_page_of_fic: bool,
    already_completed: bool,
) -> InlineKeyboardMarkup:
    """Основная клавиатура чтения (3 ряда + опциональный ряд «Дочитано»)."""
    b = InlineKeyboardBuilder()

    # Ряд 1: страницы
    prev_btn = (
        _btn(
            "◀ Назад",
            ReadNav(a="prev", f=fic_id, c=chapter_no, p=page_no - 1).pack(),
        )
        if page_no > 1
        else _btn(" ", _NOOP)
    )
    counter_btn = _btn(f"📄 {page_no}/{total_pages}", _NOOP)
    if page_no < total_pages:
        next_btn = _btn(
            "Дальше ▶",
            ReadNav(a="next", f=fic_id, c=chapter_no, p=page_no + 1).pack(),
        )
    elif not is_last_page_of_fic:
        next_btn = _btn(
            "Глава ⏭",
            ReadNav(a="chapter", f=fic_id, c=chapter_no + 1, p=1).pack(),
        )
    else:
        next_btn = _btn(" ", _NOOP)
    b.row(prev_btn, counter_btn, next_btn)

    # Ряд 2: главы + TOC
    if chapter_no > 1:
        ch_prev_btn = _btn(
            "⏮ Глава",
            ReadNav(a="chapter", f=fic_id, c=chapter_no - 1, p=1).pack(),
        )
    else:
        ch_prev_btn = _btn(" ", _NOOP)
    toc_btn = _btn(
        "📖 Оглавление",
        ReadNav(a="toc", f=fic_id, c=chapter_no, p=page_no).pack(),
    )
    if chapter_no < total_chapters:
        ch_next_btn = _btn(
            "Глава ⏭",
            ReadNav(a="chapter", f=fic_id, c=chapter_no + 1, p=1).pack(),
        )
    else:
        ch_next_btn = _btn(" ", _NOOP)
    b.row(ch_prev_btn, toc_btn, ch_next_btn)

    # Ряд 3: действия
    bookmark_btn = _btn(
        "📑" if is_bookmarked else "🔖",
        ReadNav(a="bookmark", f=fic_id, c=chapter_no, p=page_no).pack(),
    )
    like_btn = _btn(
        "❤️" if is_liked else "🤍",
        ReadNav(a="like", f=fic_id, c=chapter_no, p=page_no).pack(),
    )
    report_btn = _btn(
        "⚠️",
        ReadNav(a="report", f=fic_id, c=chapter_no, p=page_no).pack(),
    )
    b.row(bookmark_btn, like_btn, report_btn)

    # Опциональный ряд: «Дочитано» — только на последней странице фика.
    if is_last_page_of_fic and not already_completed:
        b.row(
            _btn(
                "✓ Дочитано",
                ReadNav(a="complete", f=fic_id, c=chapter_no, p=page_no).pack(),
            )
        )

    # Футер: всегда даём выход в каталог, чтобы юзер не «застрял» в чтении.
    b.row(_btn("⟵ Каталог", "menu:browse"))
    return b.as_markup()


def toc_kb(
    *, fic_id: int, chapters: list[Chapter], current_chapter_no: int
) -> InlineKeyboardMarkup:
    """Оглавление: список глав → переход на стр.1 главы."""
    b = InlineKeyboardBuilder()
    for c in chapters:
        marker = "▶ " if int(c.number) == current_chapter_no else ""
        b.row(
            _btn(
                f"{marker}Глава {int(c.number)}. {c.title}",
                ReadNav(a="chapter", f=fic_id, c=int(c.number), p=1).pack(),
            )
        )
    return b.as_markup()


def feed_kb(
    *,
    items: list[FeedItem],
    kind: str,
    fandom_id: int,
    page: int,
    has_more: bool,
) -> InlineKeyboardMarkup:
    """Клавиатура ленты каталога.

    Если задан `fandom_id` — добавляем кнопку «🔎 Поиск в этом фандоме»,
    она запускает quick-search с предустановленным фильтром по этому фандому
    (юзер ищет «арка» внутри Наруто, не выходя в общий поиск).
    """
    from app.presentation.bot.callback_data.browse import BrowseCD, QuickQCD

    b = InlineKeyboardBuilder()
    for item in items:
        label = item.title
        if item.author_nick:
            label = f"{label} — {item.author_nick}"
        # Telegram ограничивает длину кнопки; обрежем на ~60 символов.
        if len(label) > 60:
            label = label[:57] + "…"
        b.row(_btn(label, ReadNav(a="open", f=int(item.fic_id)).pack()))

    prev_btn = (
        _btn("◀", BrowseCD(a=kind, fd=fandom_id, pg=page - 1).pack())
        if page > 0
        else _btn(" ", _NOOP)
    )
    page_btn = _btn(f"стр. {page + 1}", _NOOP)
    next_btn = (
        _btn("▶", BrowseCD(a=kind, fd=fandom_id, pg=page + 1).pack())
        if has_more
        else _btn(" ", _NOOP)
    )
    b.row(prev_btn, page_btn, next_btn)
    if fandom_id:
        # Поиск внутри этого фандома: пробрасываем fandom_id в callback,
        # чтобы handler сразу выставил `s_fandoms=[fandom_id]` перед FSM.
        b.row(
            _btn(
                "🔎 Поиск в этом фандоме",
                QuickQCD(a="in_fandom", fd=int(fandom_id)).pack(),
            )
        )
    b.row(_btn("⟵ Каталог", BrowseCD(a="root").pack()))
    return b.as_markup()
