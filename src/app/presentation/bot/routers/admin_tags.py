"""Роутер админа: merge-кандидаты тегов + выполнение merge."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka, inject

from app.application.reference.tags_merge import (
    ListMergeCandidatesUseCase,
    MergeTagsCommand,
    MergeTagsUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.presentation.bot.callback_data.admin import AdminCD, TagAdminCD
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.keyboards.admin_tags import build_tag_candidates_kb
from app.presentation.bot.ui_helpers import render

log = get_logger(__name__)
router = Router(name="admin_tags")


@router.callback_query(AdminCD.filter(F.action == "tags"), IsAdmin())
@router.callback_query(TagAdminCD.filter(F.action == "candidates"), IsAdmin())
@inject
async def show_candidates(
    cb: CallbackQuery,
    list_uc: FromDishka[ListMergeCandidatesUseCase],
) -> None:
    candidates = await list_uc(limit=20)
    items = [
        (int(c.canonical_id), str(c.canonical_name), int(c.source_id), str(c.source_name))
        for c in candidates
    ]
    if not items:
        await render(cb, "🏷️ Кандидатов на объединение тегов не найдено.")
        await cb.answer()
        return
    await render(
        cb,
        f"🏷️ <b>Объединение похожих тегов</b>\n\n"
        f"Найдено {len(items)} пар. Клик по паре — объединить "
        f"(второй тег привяжется к первому):",
        reply_markup=build_tag_candidates_kb(items),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(TagAdminCD.filter(F.action == "merge"), IsAdmin())
@inject
async def do_merge(
    cb: CallbackQuery,
    callback_data: TagAdminCD,
    uc: FromDishka[MergeTagsUseCase],
    list_uc: FromDishka[ListMergeCandidatesUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    try:
        result = await uc(
            MergeTagsCommand(
                actor_id=cb.from_user.id,
                canonical_id=callback_data.canonical_id,
                source_ids=[callback_data.source_id],
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer(f"✅ Объединено: {result.rows_reassigned} связок переписано")

    # Обновим список кандидатов — одна пара ушла.
    candidates = await list_uc(limit=20)
    items = [
        (int(c.canonical_id), str(c.canonical_name), int(c.source_id), str(c.source_name))
        for c in candidates
    ]
    if not items:
        await render(
            cb,
            f"✅ Объединено ({result.rows_reassigned} связок).\n\n"
            "Больше пар-кандидатов не найдено.",
        )
        return
    await render(
        cb,
        f"✅ Объединено ({result.rows_reassigned} связок).\n\nОсталось пар: {len(items)}.",
        reply_markup=build_tag_candidates_kb(items),
    )
