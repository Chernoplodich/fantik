"""Админ-роутер: список заявок на новый фандом + одобрение / отклонение."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.reference.ports import (
    FandomProposalRow,
    IFandomProposalRepository,
)
from app.application.reference.proposals import (
    ApproveFandomProposalCommand,
    ApproveFandomProposalUseCase,
    ListPendingFandomProposalsUseCase,
    RejectFandomProposalCommand,
    RejectFandomProposalUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.domain.reference.value_objects import ProposalId
from app.presentation.bot.callback_data.admin import (
    AdminCD,
    FandomProposalAdminCD,
)
from app.presentation.bot.fandom_categories import category_long_label
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.fsm.states.admin_proposals import (
    FandomProposalReviewFlow,
)
from app.presentation.bot.keyboards.admin_fandom_proposals import (
    build_proposal_approve_category_kb,
    build_proposal_card_kb,
    build_proposals_list_kb,
)
from app.presentation.bot.ui_helpers import render

log = get_logger(__name__)
router = Router(name="admin_proposals")


def _format_card(row: FandomProposalRow) -> str:
    lines = [
        f"📋 <b>Заявка #{int(row.id)}</b>",
        "",
        f"Название: <b>{escape(row.name)}</b>",
        f"Категория: {category_long_label(row.category_hint)} "
        f"(<code>{escape(row.category_hint)}</code>)",
        f"Автор: <code>{int(row.requested_by)}</code>",
    ]
    if row.comment:
        lines.append(f"Комментарий автора: {escape(row.comment)}")
    lines.append(f"Статус: {row.status}")
    lines.append(f"Создана: {row.created_at:%Y-%m-%d %H:%M UTC}")
    return "\n".join(lines)


@router.callback_query(AdminCD.filter(F.action == "proposals"), IsAdmin())
@inject
async def show_proposals(
    cb: CallbackQuery,
    list_uc: FromDishka[ListPendingFandomProposalsUseCase],
) -> None:
    rows = await list_uc(limit=50)
    body = f"📋 <b>Заявки на фандом</b>\n\nОткрытых: <b>{len(rows)}</b>"
    await render(cb, body, reply_markup=build_proposals_list_kb(rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(FandomProposalAdminCD.filter(F.action == "open"), IsAdmin())
@inject
async def open_proposal(
    cb: CallbackQuery,
    callback_data: FandomProposalAdminCD,
    repo: FromDishka[IFandomProposalRepository],
) -> None:
    proposal = await repo.get(ProposalId(int(callback_data.pid)))
    if proposal is None:
        await cb.answer("Заявка не найдена.", show_alert=True)
        return
    row = FandomProposalRow(
        id=proposal.id,
        name=proposal.name,
        category_hint=proposal.category_hint,
        comment=proposal.comment,
        requested_by=proposal.requested_by,
        status=proposal.status.value,
        reviewed_by=proposal.reviewed_by,
        reviewed_at=proposal.reviewed_at,
        decision_comment=proposal.decision_comment,
        created_fandom_id=proposal.created_fandom_id,
        created_at=proposal.created_at or proposal.created_at,  # type: ignore[arg-type]
    )
    await render(
        cb,
        _format_card(row),
        reply_markup=build_proposal_card_kb(int(proposal.id)),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(FandomProposalAdminCD.filter(F.action == "approve_pick"), IsAdmin())
@inject
async def approve_pick_category(
    cb: CallbackQuery,
    callback_data: FandomProposalAdminCD,
    repo: FromDishka[IFandomProposalRepository],
) -> None:
    """Шаг 1 approve: показать picker категорий с предзаполненной категорией."""
    proposal = await repo.get(ProposalId(int(callback_data.pid)))
    if proposal is None:
        await cb.answer("Заявка не найдена.", show_alert=True)
        return
    body = (
        f"📋 <b>Заявка #{int(proposal.id)}</b>\n\n"
        f"Название: <b>{escape(proposal.name)}</b>\n\n"
        "Выбери категорию для фандома (предложенная отмечена ✅).\n"
        "Клик создаст фандом."
    )
    await render(
        cb,
        body,
        reply_markup=build_proposal_approve_category_kb(
            pid=int(proposal.id), current_cat=proposal.category_hint
        ),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(FandomProposalAdminCD.filter(F.action == "approve_do"), IsAdmin())
@inject
async def approve_do(
    cb: CallbackQuery,
    callback_data: FandomProposalAdminCD,
    approve_uc: FromDishka[ApproveFandomProposalUseCase],
    list_uc: FromDishka[ListPendingFandomProposalsUseCase],
) -> None:
    """Шаг 2 approve: создаёт фандом с выбранной категорией."""
    if cb.from_user is None:
        return  # type: ignore[unreachable]
    try:
        result = await approve_uc(
            ApproveFandomProposalCommand(
                actor_id=cb.from_user.id,
                proposal_id=int(callback_data.pid),
                category=callback_data.cat or None,
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer(f"✅ Одобрено — фандом #{int(result.fandom_id)}", show_alert=False)
    rows = await list_uc(limit=50)
    body = (
        "📋 <b>Заявки на фандом</b>\n\n"
        f"Открытых: <b>{len(rows)}</b>\n\n"
        f"✅ Заявка #{int(result.proposal_id)} одобрена."
    )
    await render(cb, body, reply_markup=build_proposals_list_kb(rows), parse_mode="HTML")


# ---------- reject: вход + ввод причины ----------


@router.callback_query(FandomProposalAdminCD.filter(F.action == "reject"), IsAdmin())
async def reject_proposal_start(
    cb: CallbackQuery,
    callback_data: FandomProposalAdminCD,
    state: FSMContext,
) -> None:
    await state.set_state(FandomProposalReviewFlow.waiting_reject_reason)
    await state.update_data(_reject_pid=int(callback_data.pid))
    body = (
        "❌ <b>Отклонить заявку</b>\n\n"
        "Пришли причину одним сообщением (до 500 символов).\n"
        "Можно прислать «-», чтобы отклонить без комментария."
    )
    await render(cb, body, parse_mode="HTML")
    await cb.answer()


@router.message(
    FandomProposalReviewFlow.waiting_reject_reason,
    F.chat.type == "private",
    IsAdmin(),
)
@inject
async def reject_proposal_reason(
    message: Message,
    state: FSMContext,
    reject_uc: FromDishka[RejectFandomProposalUseCase],
    list_uc: FromDishka[ListPendingFandomProposalsUseCase],
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    pid = int(data.get("_reject_pid") or 0)
    if not pid:
        await state.clear()
        await message.answer("Ошибка: не указана заявка.")
        return
    raw = (message.text or "").strip()
    reason = None if raw in {"-", ""} else raw[:500]
    try:
        await reject_uc(
            RejectFandomProposalCommand(
                actor_id=message.from_user.id,
                proposal_id=pid,
                reason=reason,
            )
        )
    except DomainError as e:
        await message.answer(f"❌ {e}")
        await state.clear()
        return
    await state.clear()
    rows = await list_uc(limit=50)
    body = (
        f"❌ Заявка #{pid} отклонена.\n\n📋 <b>Заявки на фандом</b>\nОткрытых: <b>{len(rows)}</b>"
    )
    await message.answer(body, reply_markup=build_proposals_list_kb(rows), parse_mode="HTML")
