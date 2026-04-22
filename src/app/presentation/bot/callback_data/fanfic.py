"""CallbackData для операций автора над фиком / главой."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class FanficCD(CallbackData, prefix="fic"):
    action: str  # view / edit / submit / cancel / delete / add_chapter / revise / archive
    fic_id: int


class ChapterCD(CallbackData, prefix="ch"):
    action: str  # view / edit / delete
    chapter_id: int


class FandomPickCD(CallbackData, prefix="fandom"):
    action: str  # pick / page
    page: int = 0
    fandom_id: int = 0


class AgeRatingCD(CallbackData, prefix="ager"):
    rating_id: int


class EditFieldCD(CallbackData, prefix="edf"):
    """Выбор поля для правки в меню редактирования фика."""

    field: str  # title / summary / fandom / age_rating / tags / cover / cover_clear / back
    fic_id: int


class ChapterListCD(CallbackData, prefix="chlst"):
    """Открыть главу из списка (для автора — управление)."""

    fic_id: int
    chapter_id: int


class ChapterActionCD(CallbackData, prefix="chact"):
    """Действие над главой (view/edit/delete/confirm_delete/cancel_delete)."""

    action: str
    chapter_id: int
