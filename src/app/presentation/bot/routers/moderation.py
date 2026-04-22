"""Модерационная панель: pick_next, карточка, approve/reject/unlock."""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.fanfics.ports import IChapterRepository, IReferenceReader, ITagRepository
from app.application.users.ports import IUserRepository
from app.application.moderation.approve import ApproveCommand, ApproveUseCase
from app.application.moderation.list_reasons import ListReasonsUseCase
from app.application.moderation.pick_next import (
    PickNextCommand,
    PickNextUseCase,
)
from app.application.moderation.reject import RejectCommand, RejectUseCase
from app.application.moderation.release_stale_locks import (
    ReleaseStaleLocksUseCase,
)
from app.application.moderation.unlock import UnlockCaseUseCase, UnlockCommand
from app.core.errors import DomainError
from app.domain.shared.types import ChapterId, FandomId
from app.presentation.bot.callback_data.moderation import ModCD, ReasonCD
from app.presentation.bot.filters.role import IsAdmin, IsModerator
from app.presentation.bot.fsm.states.moderation_reject import (
    ModerationRejectStates,
)
from app.presentation.bot.keyboards.moderation import (
    build_mod_card_kb,
    build_mod_menu_kb,
    build_reason_picker_kb,
    build_reject_preview_kb,
)
from app.presentation.bot.texts.ru import t

router = Router(name="moderation")


# ---------- menu ----------


@router.message(Command("mod_queue"), IsModerator())
@router.callback_query(F.data == "menu:mod", IsModerator())
@router.callback_query(ModCD.filter(F.action == "menu"), IsModerator())
async def show_mod_menu(event: Message | CallbackQuery) -> None:
    text = t("mod_menu")
    if isinstance(event, CallbackQuery):
        if event.message is not None:
            await event.message.answer(text, reply_markup=build_mod_menu_kb())
        await event.answer()
    else:
        await event.answer(text, reply_markup=build_mod_menu_kb())


# ---------- pick next ----------


@router.callback_query(ModCD.filter(F.action == "pick"), IsModerator())
@inject
async def pick_next(
    cb: CallbackQuery,
    pick_uc: FromDishka[PickNextUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
    users_repo: FromDishka[IUserRepository],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await pick_uc(PickNextCommand(moderator_id=cb.from_user.id))
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    if result.card is None:
        await cb.message.answer(t("mod_queue_empty"))
        await cb.answer()
        return

    fic = result.card.fic_bundle.fic
    chapters = result.card.fic_bundle.chapters
    tags = await tags_repo.list_by_fic(fic.id)
    fandom = await reference.get_fandom(FandomId(int(fic.fandom_id)))
    rating = await reference.get_age_rating(int(fic.age_rating_id))
    author = await users_repo.get(fic.author_id)

    from html import escape as _h

    author_line = _build_author_line(
        author_id=int(fic.author_id),
        author_nick=author.author_nick if author else None,
        username=author.username if author else None,
    )

    text = t(
        "mod_card_header",
        case_id=int(result.card.case.id),
        kind=result.card.case.kind.value,
        author_line=author_line,
        title=_h(str(fic.title)),
        fandom=_h(fandom.name) if fandom else "—",
        rating=_h(rating.code) if rating else "—",
        tags=_h(", ".join(str(t.name) for t in tags)) or "—",
        chapters_count=fic.chapters_count,
        summary=_h(str(fic.summary)),
    )
    chapter_ids = [(int(ch.id), int(ch.number)) for ch in chapters]
    kb = build_mod_card_kb(case_id=int(result.card.case.id), chapter_ids=chapter_ids)

    if fic.cover_file_id:
        try:
            await cb.message.answer_photo(
                photo=fic.cover_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:  # noqa: BLE001 — fallback на текст если file_id невалиден
            await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


# ---------- read chapter ----------


@router.callback_query(
    ModCD.filter(F.action == "read_chapter"), IsModerator()
)
@inject
async def read_chapter(
    cb: CallbackQuery,
    callback_data: ModCD,
    chapters: FromDishka[IChapterRepository],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    ch = await chapters.get(ChapterId(callback_data.chapter_id))
    if ch is None:
        await cb.answer("Глава не найдена.", show_alert=True)
        return
    text = t("mod_chapter_header", number=int(ch.number), title=str(ch.title), text=ch.text)
    # Пытаемся отдать entities автора — они в Telegram API формате.
    from aiogram.types import MessageEntity

    entities: list[MessageEntity] = []
    for e in ch.entities:
        try:
            entities.append(MessageEntity.model_validate(e))
        except Exception:  # noqa: BLE001
            continue
    # Заголовок добавляет сдвиг — сбрасываем entities, показываем «сырой» текст без заголовка,
    # иначе offsets не совпадают. Посылаем отдельным сообщением.
    await cb.message.answer(f"📖 Глава {int(ch.number)}. {str(ch.title)}")
    await cb.message.answer(ch.text, entities=entities or None)
    await cb.answer()


# ---------- approve ----------


@router.callback_query(ModCD.filter(F.action == "approve"), IsModerator())
@inject
async def approve(
    cb: CallbackQuery,
    callback_data: ModCD,
    approve_uc: FromDishka[ApproveUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    try:
        await approve_uc(
            ApproveCommand(case_id=callback_data.case_id, moderator_id=cb.from_user.id)
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    await _deactivate_card(cb)
    if cb.message is not None:
        await cb.message.answer(
            t("mod_decision_applied"), reply_markup=build_mod_menu_kb()
        )
    await cb.answer()


# ---------- reject flow ----------


@router.callback_query(ModCD.filter(F.action == "reject"), IsModerator())
@inject
async def reject_start(
    cb: CallbackQuery,
    callback_data: ModCD,
    state: FSMContext,
    reasons_uc: FromDishka[ListReasonsUseCase],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    reasons = await reasons_uc()
    await state.set_state(ModerationRejectStates.picking_reasons)
    await state.update_data(case_id=callback_data.case_id, reason_ids=[], comment=None)
    await cb.message.answer(
        t("mod_reasons_prompt"),
        reply_markup=build_reason_picker_kb(
            case_id=callback_data.case_id, reasons=reasons, selected=set()
        ),
    )
    await cb.answer()


@router.callback_query(
    ModerationRejectStates.picking_reasons, ReasonCD.filter(F.action == "toggle")
)
@inject
async def reject_toggle_reason(
    cb: CallbackQuery,
    callback_data: ReasonCD,
    state: FSMContext,
    reasons_uc: FromDishka[ListReasonsUseCase],
) -> None:
    data = await state.get_data()
    selected: list[int] = list(data.get("reason_ids") or [])
    rid = int(callback_data.reason_id)
    if rid in selected:
        selected.remove(rid)
    else:
        selected.append(rid)
    await state.update_data(reason_ids=selected)
    reasons = await reasons_uc()
    if cb.message is not None:
        await cb.message.edit_reply_markup(
            reply_markup=build_reason_picker_kb(
                case_id=callback_data.case_id,
                reasons=reasons,
                selected=set(selected),
            )
        )
    await cb.answer()


@router.callback_query(
    ModerationRejectStates.picking_reasons, ReasonCD.filter(F.action == "confirm")
)
async def reject_go_to_comment(
    cb: CallbackQuery,
    callback_data: ReasonCD,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    if not data.get("reason_ids"):
        await cb.answer("Выбери хотя бы одну причину.", show_alert=True)
        return
    await state.set_state(ModerationRejectStates.waiting_comment)
    if cb.message is not None:
        await cb.message.answer(t("mod_comment_prompt"))
    await cb.answer()


@router.message(ModerationRejectStates.waiting_comment)
@inject
async def reject_comment(
    message: Message,
    state: FSMContext,
    reasons_uc: FromDishka[ListReasonsUseCase],
) -> None:
    if not message.text:
        await message.answer(t("fic_expect_text"))
        return
    comment = None if message.text.strip() == "-" else message.text
    entities = _dump_entities(message.entities) if comment else []
    await state.update_data(comment=comment, comment_entities=entities)
    data = await state.get_data()

    from html import escape as _h

    all_reasons = {int(r.id): r for r in await reasons_uc()}
    picked = [all_reasons[int(r)] for r in data["reason_ids"] if int(r) in all_reasons]

    preview = t(
        "mod_confirm_preview",
        reasons=_h(", ".join(r.title for r in picked)),
        comment=_h(comment) if comment else "—",
    )
    await state.set_state(ModerationRejectStates.confirming)
    await message.answer(
        preview,
        reply_markup=build_reject_preview_kb(int(data["case_id"])),
        parse_mode="HTML",
    )


@router.callback_query(
    ModerationRejectStates.confirming, ModCD.filter(F.action == "reject_confirm")
)
@inject
async def reject_confirm(
    cb: CallbackQuery,
    callback_data: ModCD,
    state: FSMContext,
    reject_uc: FromDishka[RejectUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    data = await state.get_data()
    try:
        await reject_uc(
            RejectCommand(
                case_id=int(data["case_id"]),
                moderator_id=cb.from_user.id,
                reason_ids=list(data.get("reason_ids") or []),
                comment=data.get("comment"),
                comment_entities=list(data.get("comment_entities") or []),
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        await state.clear()
        return
    await state.clear()
    await _deactivate_card(cb)
    if cb.message is not None:
        await cb.message.answer(
            t("mod_decision_applied"), reply_markup=build_mod_menu_kb()
        )
    await cb.answer()


@router.callback_query(ModerationRejectStates.confirming, ModCD.filter(F.action == "menu"))
async def reject_cancel_confirm(
    cb: CallbackQuery, state: FSMContext
) -> None:
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(t("mod_menu"), reply_markup=build_mod_menu_kb())
    await cb.answer()


# ---------- unlock ----------


@router.callback_query(ModCD.filter(F.action == "unlock"), IsModerator())
@inject
async def unlock(
    cb: CallbackQuery,
    callback_data: ModCD,
    unlock_uc: FromDishka[UnlockCaseUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    try:
        await unlock_uc(
            UnlockCommand(case_id=callback_data.case_id, moderator_id=cb.from_user.id)
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    if cb.message is not None:
        await cb.message.answer(t("mod_unlocked"))
    await cb.answer()


# ---------- release stale locks (admin) ----------


@router.message(Command("release_stale_locks"), IsAdmin())
@inject
async def release_stale(
    message: Message,
    uc: FromDishka[ReleaseStaleLocksUseCase],
) -> None:
    count = await uc()
    await message.answer(t("mod_released_stale", count=count))


# ---------- helpers ----------


def _build_author_line(
    *,
    author_id: int,
    author_nick: str | None,
    username: str | None,
) -> str:
    """Строит строку автора вида `ник (@username) (id12345)` с HTML-escape.

    Если username отсутствует — просто `ник (id12345)`.
    Если author_nick отсутствует (теоретически) — `(@username) (id12345)` или `(id12345)`.
    """
    from html import escape as _h

    parts: list[str] = []
    if author_nick:
        parts.append(f"<b>{_h(author_nick)}</b>")
    if username:
        parts.append(f"(@{_h(username)})")
    parts.append(
        f'<a href="tg://user?id={author_id}">id{author_id}</a>'
    )
    return " ".join(parts)


async def _deactivate_card(cb: CallbackQuery) -> None:
    """Снять inline-клавиатуру у карточки после принятия решения.

    Защищает от повторного клика по Approve/Reject/Unlock/Read.
    """
    if cb.message is None:
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001 — не критично, если нельзя отредактировать
        pass


def _dump_entities(entities: Any) -> list[dict[str, Any]]:
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
