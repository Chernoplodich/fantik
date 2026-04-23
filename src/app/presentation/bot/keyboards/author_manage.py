"""Клавиатуры для списка «Мои работы» и карточки фика автора."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.fanfics.ports import FanficListItem
from app.domain.fanfics.entities import Chapter
from app.domain.fanfics.value_objects import FicStatus
from app.presentation.bot.callback_data.fanfic import (
    ChapterActionCD,
    ChapterListCD,
    EditFieldCD,
    FanficCD,
)


STATUS_LABELS = {
    FicStatus.DRAFT: "✏️",
    FicStatus.PENDING: "⏳",
    FicStatus.APPROVED: "✅",
    FicStatus.REJECTED: "❌",
    FicStatus.REVISING: "🔧",
    FicStatus.ARCHIVED: "📦",
}


def build_my_works_kb(items: list[FanficListItem]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for it in items:
        label = f"{STATUS_LABELS.get(it.status, '•')} {it.title}"
        b.button(
            text=label[:64],
            callback_data=FanficCD(action="view", fic_id=int(it.fic_id)).pack(),
        )
    b.button(text="➕ Новая работа", callback_data="menu:new_fic")
    b.button(text="← Главное меню", callback_data="menu:back")
    b.adjust(1)
    return b.as_markup()


def build_fanfic_card_kb(fic_id: int, status: FicStatus) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    fic_id_int = int(fic_id)
    if status in (FicStatus.DRAFT, FicStatus.REVISING):
        b.button(
            text="➕ Добавить главу",
            callback_data=FanficCD(action="add_chapter", fic_id=fic_id_int).pack(),
        )
        b.button(
            text="📚 Главы",
            callback_data=FanficCD(action="chapters", fic_id=fic_id_int).pack(),
        )
        b.button(
            text="📤 Отправить на модерацию",
            callback_data=FanficCD(action="submit", fic_id=fic_id_int).pack(),
        )
        b.button(
            text="✏️ Редактировать описание",
            callback_data=FanficCD(action="edit", fic_id=fic_id_int).pack(),
        )
    elif status == FicStatus.PENDING:
        b.button(
            text="⛔ Отменить подачу",
            callback_data=FanficCD(action="cancel", fic_id=fic_id_int).pack(),
        )
    elif status == FicStatus.REJECTED:
        b.button(
            text="🔧 Доработать",
            callback_data=FanficCD(action="revise", fic_id=fic_id_int).pack(),
        )
        b.button(
            text="📚 Главы",
            callback_data=FanficCD(action="chapters", fic_id=fic_id_int).pack(),
        )
    elif status == FicStatus.APPROVED:
        b.button(
            text="➕ Добавить главу",
            callback_data=FanficCD(action="add_chapter", fic_id=fic_id_int).pack(),
        )
        b.button(
            text="📚 Главы",
            callback_data=FanficCD(action="chapters", fic_id=fic_id_int).pack(),
        )
        # Правка approved-фика требует повторной модерации. Первый тап — диалог
        # с пояснением; после «Начать правку» фик уходит в REVISING и пользователь
        # получает обычное меню правки.
        b.button(
            text="🔄 Внести правку",
            callback_data=FanficCD(action="request_revise", fic_id=fic_id_int).pack(),
        )
    b.button(text="← Мои работы", callback_data="menu:my_works")
    b.adjust(1)
    return b.as_markup()


def build_edit_menu_kb(fic_id: int, *, has_cover: bool) -> InlineKeyboardMarkup:
    """Меню выбора поля для правки."""
    b = InlineKeyboardBuilder()
    for field, label in (
        ("title", "✏️ Название"),
        ("summary", "✏️ Аннотация"),
        ("fandom", "✏️ Фандом"),
        ("age_rating", "✏️ Возрастной рейтинг"),
        ("tags", "✏️ Теги"),
    ):
        b.button(
            text=label,
            callback_data=EditFieldCD(field=field, fic_id=fic_id).pack(),
        )
    if has_cover:
        b.button(
            text="🖼 Заменить обложку",
            callback_data=EditFieldCD(field="cover", fic_id=fic_id).pack(),
        )
        b.button(
            text="🗑 Удалить обложку",
            callback_data=EditFieldCD(field="cover_clear", fic_id=fic_id).pack(),
        )
    else:
        b.button(
            text="🖼 Загрузить обложку",
            callback_data=EditFieldCD(field="cover", fic_id=fic_id).pack(),
        )
    b.button(
        text="← К работе",
        callback_data=FanficCD(action="view", fic_id=fic_id).pack(),
    )
    b.adjust(1)
    return b.as_markup()


def build_chapter_list_kb(
    *, fic_id: int, chapters: list[Chapter], editable: bool
) -> InlineKeyboardMarkup:
    """Список глав автору с переходом на карточку главы (для управления)."""
    b = InlineKeyboardBuilder()
    for ch in chapters:
        status_mark = (
            "✅"
            if ch.status == FicStatus.APPROVED
            else ("⏳" if ch.status == FicStatus.PENDING else "✏️")
        )
        b.button(
            text=f"{status_mark} Глава {int(ch.number)}: {str(ch.title)[:40]}",
            callback_data=ChapterListCD(fic_id=fic_id, chapter_id=int(ch.id)).pack(),
        )
    b.button(
        text="← К работе",
        callback_data=FanficCD(action="view", fic_id=fic_id).pack(),
    )
    b.adjust(1)
    return b.as_markup()


def build_chapter_actions_kb(
    *, fic_id: int, chapter_id: int, status: FicStatus
) -> InlineKeyboardMarkup:
    """Действия над главой: Править / Удалить — только для не-approved."""
    b = InlineKeyboardBuilder()
    if status in (FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING):
        b.button(
            text="✏️ Изменить текст",
            callback_data=ChapterActionCD(action="edit", chapter_id=chapter_id).pack(),
        )
        if status == FicStatus.DRAFT:
            b.button(
                text="🗑 Удалить главу",
                callback_data=ChapterActionCD(action="delete", chapter_id=chapter_id).pack(),
            )
    b.button(
        text="← К списку глав",
        callback_data=FanficCD(action="chapters", fic_id=fic_id).pack(),
    )
    b.adjust(1)
    return b.as_markup()


def build_delete_confirm_kb(*, chapter_id: int, fic_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="🗑 Удалить безвозвратно",
        callback_data=ChapterActionCD(action="confirm_delete", chapter_id=chapter_id).pack(),
    )
    b.button(
        text="Отмена",
        callback_data=ChapterActionCD(action="cancel_delete", chapter_id=chapter_id).pack(),
    )
    b.adjust(1)
    return b.as_markup()
