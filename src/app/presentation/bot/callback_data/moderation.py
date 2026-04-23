"""CallbackData для модерационной панели."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class ModCD(CallbackData, prefix="mod"):
    # actions:
    #   pick / approve / reject / unlock / menu / release_stale
    #   read_chapter   — открыть страницу 1 указанной главы (in-place навигация)
    #   mod_page       — листание страниц в пределах текущей главы (page_no)
    #   back_to_card   — вернуться к карточке фика (из чтения главы)
    action: str
    case_id: int = 0
    chapter_id: int = 0
    page_no: int = 0


class ReasonCD(CallbackData, prefix="rsn"):
    action: str  # toggle / confirm
    case_id: int
    reason_id: int = 0
