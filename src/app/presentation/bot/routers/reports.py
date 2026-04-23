"""Роутер жалоб: приём от читателей + модераторская вкладка."""

from __future__ import annotations

from html import escape as _h

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.reports.create_report import (
    CreateReportCommand,
    CreateReportUseCase,
)
from app.application.reports.handle_report import (
    HandleReportCommand,
    HandleReportUseCase,
)
from app.application.reports.list_open_reports import (
    ListOpenReportsCommand,
    ListOpenReportsUseCase,
)
from app.application.reports.ports import IReportRepository
from app.application.users.ports import IUserRepository
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.domain.reports.value_objects import (
    REPORT_REASON_TITLES,
    ReportTarget,
)
from app.domain.shared.types import ChapterId, FanficId, ReportId
from app.presentation.bot.callback_data.social import (
    RepMod,
    RepReason,
    RepStart,
)
from app.presentation.bot.filters.role import IsModerator
from app.presentation.bot.fsm.states.report import ReportFlow
from app.presentation.bot.keyboards.social import (
    report_card_kb,
    report_reason_picker_kb,
    reports_list_kb,
)

log = get_logger(__name__)
router = Router(name="reports")


_LIST_PAGE_SIZE = 10


# ---------- reader side: start FSM ----------


@router.callback_query(RepStart.filter())
async def report_start(
    cb: CallbackQuery,
    callback_data: RepStart,
    state: FSMContext,
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    target_type = ReportTarget.FANFIC if callback_data.t == "fic" else ReportTarget.CHAPTER
    await state.set_state(ReportFlow.waiting_reason)
    await state.update_data(
        target_type=target_type.value,
        target_id=int(callback_data.id),
    )
    await cb.message.answer(
        "Выбери причину жалобы:",
        reply_markup=report_reason_picker_kb(),
    )
    await cb.answer()


@router.callback_query(ReportFlow.waiting_reason, RepReason.filter())
async def report_pick_reason(
    cb: CallbackQuery,
    callback_data: RepReason,
    state: FSMContext,
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    if callback_data.code not in REPORT_REASON_TITLES:
        await cb.answer("Неизвестная причина.", show_alert=True)
        return
    await state.update_data(reason_code=callback_data.code)
    await state.set_state(ReportFlow.waiting_comment)
    await cb.message.answer(
        "Опиши кратко, в чём проблема (до 2000 символов). "
        "Или отправь «-», чтобы пропустить комментарий."
    )
    await cb.answer()


@router.message(ReportFlow.waiting_comment)
@inject
async def report_submit(
    message: Message,
    state: FSMContext,
    uc: FromDishka[CreateReportUseCase],
) -> None:
    if message.from_user is None:
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Ожидался текст или «-».")
        return
    comment: str | None = None if raw == "-" else raw
    entities = (
        [e.model_dump(exclude_none=True) for e in (message.entities or [])] if comment else []
    )

    data = await state.get_data()
    target_type_raw = str(data.get("target_type") or "")
    target_id = int(data.get("target_id") or 0)
    reason_code = data.get("reason_code")
    if not target_type_raw or target_id == 0 or reason_code is None:
        await state.clear()
        await message.answer("Сессия жалобы потеряна. Начни заново с карточки фика.")
        return

    try:
        result = await uc(
            CreateReportCommand(
                reporter_id=message.from_user.id,
                target_type=ReportTarget(target_type_raw),
                target_id=target_id,
                reason_code=str(reason_code),
                text=comment,
                text_entities=entities,
                notify_reporter=True,
            )
        )
    except DomainError as e:
        await state.clear()
        await message.answer(str(e) or "Не удалось принять жалобу.")
        return

    await state.clear()
    if result.created:
        await message.answer("✅ Жалоба принята. Модератор рассмотрит её в ближайшее время.")
    else:
        await message.answer(
            "✅ У тебя уже есть открытая жалоба на этот объект — модератор увидит её."
        )


# ---------- moderator side: list + card ----------


@router.callback_query(RepMod.filter(F.a == "list"), IsModerator())
@inject
async def mod_list_reports(
    cb: CallbackQuery,
    callback_data: RepMod,
    uc: FromDishka[ListOpenReportsUseCase],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    page = max(int(callback_data.p), 0)
    result = await uc(ListOpenReportsCommand(limit=_LIST_PAGE_SIZE, offset=page * _LIST_PAGE_SIZE))
    has_more = (page + 1) * _LIST_PAGE_SIZE < result.total
    text = f"⚠️ Открытые жалобы: {result.total}" if result.total else "⚠️ Открытых жалоб нет."
    kb = reports_list_kb(items=result.items, page=page, has_more=has_more)
    try:
        await cb.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(RepMod.filter(F.a == "card"), IsModerator())
@inject
async def mod_report_card(
    cb: CallbackQuery,
    callback_data: RepMod,
    reports: FromDishka[IReportRepository],
    fanfics: FromDishka[IFanficRepository],
    chapters: FromDishka[IChapterRepository],
    users: FromDishka[IUserRepository],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    report = await reports.get(ReportId(int(callback_data.id)))
    if report is None:
        await cb.answer("Жалоба не найдена.", show_alert=True)
        return
    reporter = await users.get(report.reporter_id)
    reporter_label = (
        f"@{reporter.username}"
        if reporter and reporter.username
        else f"id{int(report.reporter_id)}"
    )

    target_line, can_action = await _build_target_line(
        report.target_type, report.target_id, fanfics, chapters
    )

    reason_title = (
        REPORT_REASON_TITLES.get(report.reason_code, report.reason_code)
        if report.reason_code
        else "—"
    )
    text_block = _h(report.text) if report.text else "—"
    text = (
        f"<b>Жалоба #{int(report.id)}</b>\n\n"
        f"От: {_h(reporter_label)}\n"
        f"Объект: {target_line}\n"
        f"Причина: {_h(str(reason_title))}\n"
        f"\n<b>Комментарий:</b>\n{text_block}"
    )
    kb = report_card_kb(report_id=int(report.id), can_action=can_action)
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)  # type: ignore[union-attr]
    except TelegramBadRequest:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


@router.callback_query(RepMod.filter(F.a == "dismiss"), IsModerator())
@inject
async def mod_report_dismiss(
    cb: CallbackQuery,
    callback_data: RepMod,
    uc: FromDishka[HandleReportUseCase],
    list_uc: FromDishka[ListOpenReportsUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        await uc(
            HandleReportCommand(
                report_id=int(callback_data.id),
                moderator_id=cb.from_user.id,
                decision="dismiss",
                comment=None,
                action_kind=None,
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("❎ Жалоба отклонена")
    await _rerender_list(cb, list_uc, page=0)


@router.callback_query(RepMod.filter(F.a == "action"), IsModerator())
@inject
async def mod_report_action(
    cb: CallbackQuery,
    callback_data: RepMod,
    uc: FromDishka[HandleReportUseCase],
    list_uc: FromDishka[ListOpenReportsUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await uc(
            HandleReportCommand(
                report_id=int(callback_data.id),
                moderator_id=cb.from_user.id,
                decision="action",
                comment=None,
                action_kind="archive",
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    msg = (
        f"🗑 Фик #{result.archived_fic_id} архивирован"
        if result.archived_fic_id
        else "🗑 Action применён"
    )
    await cb.answer(msg)
    await _rerender_list(cb, list_uc, page=0)


# ---------- helpers ----------


async def _build_target_line(
    target_type: ReportTarget,
    target_id: int,
    fanfics: IFanficRepository,
    chapters: IChapterRepository,
) -> tuple[str, bool]:
    """Вернуть (human-readable строка объекта, можно ли применить action).

    can_action=True только для жалоб на фик (в MVP action = архив фика).
    """
    if target_type == ReportTarget.FANFIC:
        fic = await fanfics.get(FanficId(target_id))
        if fic is None:
            return (f"фик #{target_id} (не найден)", False)
        return (
            f"фик #{int(fic.id)} «{_h(str(fic.title))}»",
            True,
        )
    if target_type == ReportTarget.CHAPTER:
        ch = await chapters.get(ChapterId(target_id))
        if ch is None:
            return (f"глава #{target_id} (не найдена)", False)
        fic = await fanfics.get(ch.fic_id)
        title = str(fic.title) if fic else ""
        # Для главы action пока не поддержан (архивация только фика целиком —
        # модератор должен открыть жалобу на фик).
        return (
            f"глава {int(ch.number)} фика #{int(ch.fic_id)} «{_h(title)}»",
            False,
        )
    return (f"{target_type.value}#{target_id}", False)


async def _rerender_list(
    cb: CallbackQuery,
    list_uc: ListOpenReportsUseCase,
    *,
    page: int,
) -> None:
    if cb.message is None:
        return
    result = await list_uc(
        ListOpenReportsCommand(limit=_LIST_PAGE_SIZE, offset=page * _LIST_PAGE_SIZE)
    )
    has_more = (page + 1) * _LIST_PAGE_SIZE < result.total
    text = f"⚠️ Открытые жалобы: {result.total}" if result.total else "⚠️ Открытых жалоб нет."
    kb = reports_list_kb(items=result.items, page=page, has_more=has_more)
    try:
        await cb.message.edit_text(text, reply_markup=kb)  # type: ignore[union-attr]
    except TelegramBadRequest:
        await cb.message.answer(text, reply_markup=kb)
