"""Роутер: список моих работ + карточка фика + submit/cancel/revise/add_chapter."""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.fanfics.add_chapter import (
    AddChapterCommand,
    AddChapterUseCase,
)
from app.application.fanfics.cancel_submission import (
    CancelSubmissionCommand,
    CancelSubmissionUseCase,
)
from app.application.fanfics.delete_draft_chapter import (
    DeleteDraftChapterCommand,
    DeleteDraftChapterUseCase,
)
from app.application.fanfics.get_fanfic_draft import (
    GetFanficDraftCommand,
    GetFanficDraftUseCase,
)
from app.application.fanfics.list_my_fanfics import (
    ListMyFanficsCommand,
    ListMyFanficsUseCase,
)
from app.application.fanfics.ports import (
    IChapterRepository,
    IReferenceReader,
    ITagRepository,
)
from app.application.fanfics.revise_after_rejection import (
    ReviseAfterRejectionCommand,
    ReviseAfterRejectionUseCase,
)
from app.application.fanfics.submit_for_review import (
    SubmitForReviewCommand,
    SubmitForReviewUseCase,
)
from app.application.fanfics.update_chapter import (
    UpdateChapterCommand,
    UpdateChapterUseCase,
)
from app.application.fanfics.update_fanfic import (
    UpdateFanficCommand,
    UpdateFanficUseCase,
)
from app.core.config import Settings
from app.core.errors import DomainError
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, FanficId
from app.presentation.bot.callback_data.fanfic import (
    AgeRatingCD,
    ChapterActionCD,
    ChapterListCD,
    EditFieldCD,
    FandomPickCD,
    FanficCD,
)
from app.presentation.bot.fsm.states.add_chapter import AddChapterStates
from app.presentation.bot.fsm.states.edit_chapter import EditChapterStates
from app.presentation.bot.fsm.states.edit_fanfic import EditFanficStates
from app.presentation.bot.keyboards.author_manage import (
    build_chapter_actions_kb,
    build_chapter_list_kb,
    build_delete_confirm_kb,
    build_edit_menu_kb,
    build_fanfic_card_kb,
    build_my_works_kb,
)
from app.presentation.bot.keyboards.create_fanfic import (
    FANDOM_PAGE_SIZE,
    build_age_rating_kb,
    build_chapter_or_submit_kb,
    build_fandom_picker_kb,
)
from app.presentation.bot.routers._chapter_buffer import (
    append_chunk,
    build_chapter_compose_kb,
    dump_entities as _dump_entities,
    read_buffer,
    reset_buffer,
)
from app.presentation.bot.texts.ru import t

router = Router(name="author_manage")


# ---------- My works ----------


@router.message(Command("my_works"))
@router.callback_query(F.data == "menu:my_works")
@inject
async def show_my_works(
    event: Message | CallbackQuery,
    list_uc: FromDishka[ListMyFanficsUseCase],
) -> None:
    user_id = getattr(event.from_user, "id", None)
    if user_id is None:
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    result = await list_uc(ListMyFanficsCommand(author_id=user_id, limit=10, offset=0))
    if result.total == 0:
        text = t("my_works_empty")
    else:
        text = t("my_works_header", total=result.total)
    kb = build_my_works_kb(result.items)
    if isinstance(event, CallbackQuery):
        if event.message is not None:
            await event.message.answer(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


# ---------- View one fanfic ----------


@router.callback_query(FanficCD.filter(F.action == "view"))
@inject
async def view_fanfic(
    cb: CallbackQuery,
    callback_data: FanficCD,
    get_uc: FromDishka[GetFanficDraftUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        bundle = await get_uc(
            GetFanficDraftCommand(
                fic_id=callback_data.fic_id, author_id=cb.from_user.id
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return

    fic = bundle.fic
    from html import escape as _h

    text = t(
        "my_works_card",
        title=_h(str(fic.title)),
        status=fic.status.value,
        chapters=fic.chapters_count,
        updated=fic.updated_at.strftime("%Y-%m-%d %H:%M") if fic.updated_at else "—",
        summary=_h(str(fic.summary)),
    )
    await cb.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=build_fanfic_card_kb(int(fic.id), fic.status),
    )
    await cb.answer()


# ---------- Submit ----------


@router.callback_query(FanficCD.filter(F.action == "submit"))
@inject
async def submit_fanfic(
    cb: CallbackQuery,
    callback_data: FanficCD,
    submit_uc: FromDishka[SubmitForReviewUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    try:
        result = await submit_uc(
            SubmitForReviewCommand(
                fic_id=callback_data.fic_id, author_id=cb.from_user.id
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    if cb.message is not None:
        await cb.message.answer(
            t(
                "submit_success",
                case_id=result.case_id,
                version=result.version_no,
            )
        )
    await cb.answer()


# ---------- Cancel submission ----------


@router.callback_query(FanficCD.filter(F.action == "cancel"))
@inject
async def cancel_submission(
    cb: CallbackQuery,
    callback_data: FanficCD,
    cancel_uc: FromDishka[CancelSubmissionUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    try:
        await cancel_uc(
            CancelSubmissionCommand(
                fic_id=callback_data.fic_id, author_id=cb.from_user.id
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    if cb.message is not None:
        await cb.message.answer(t("cancel_success"))
    await cb.answer()


# ---------- Revise after rejection ----------


@router.callback_query(FanficCD.filter(F.action == "revise"))
@inject
async def revise_fanfic(
    cb: CallbackQuery,
    callback_data: FanficCD,
    revise_uc: FromDishka[ReviseAfterRejectionUseCase],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    try:
        await revise_uc(
            ReviseAfterRejectionCommand(
                fic_id=callback_data.fic_id, author_id=cb.from_user.id
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    if cb.message is not None:
        await cb.message.answer(t("revise_success"))
    await cb.answer()


# ---------- Add chapter (стоячий FSM) ----------


@router.callback_query(FanficCD.filter(F.action == "add_chapter"))
async def add_chapter_start(
    cb: CallbackQuery,
    callback_data: FanficCD,
    state: FSMContext,
) -> None:
    await state.set_state(AddChapterStates.waiting_title)
    await state.update_data(fic_id=callback_data.fic_id, chapter_title=None)
    if cb.message is not None:
        await cb.message.answer(t("fic_create_chapter_title_prompt"))
    await cb.answer()


@router.message(AddChapterStates.waiting_title)
async def add_chapter_title(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer(t("fic_expect_text"))
        return
    await state.update_data(chapter_title=message.text)
    await reset_buffer(state)
    await state.set_state(AddChapterStates.waiting_text)
    await message.answer(t("fic_create_chapter_text_prompt", max_chars=100_000))


@router.message(AddChapterStates.waiting_text, F.text)
@inject
async def add_chapter_chunk(
    message: Message,
    state: FSMContext,
    settings: FromDishka[Settings],
) -> None:
    if not message.text or message.from_user is None:
        await message.answer(t("fic_expect_text"))
        return
    u16, overflow = await append_chunk(state, message, max_chars=settings.max_chapter_chars)
    if overflow:
        await message.answer(
            t("chapter_overflow", limit=settings.max_chapter_chars),
            reply_markup=build_chapter_compose_kb(
                u16=(await read_buffer(state))[2], limit=settings.max_chapter_chars
            ),
        )
        return
    await message.answer(
        t("chapter_chunk_added", u16=u16, limit=settings.max_chapter_chars),
        reply_markup=build_chapter_compose_kb(u16=u16, limit=settings.max_chapter_chars),
    )


@router.message(AddChapterStates.waiting_text)
async def add_chapter_bad(message: Message) -> None:
    await message.answer(t("fic_expect_text"))


@router.callback_query(AddChapterStates.waiting_text, F.data == "chapter:cancel")
async def add_chapter_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await reset_buffer(state)
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(t("chapter_discarded"))
    await cb.answer()


@router.callback_query(AddChapterStates.waiting_text, F.data == "chapter:finish")
@inject
async def add_chapter_finish(
    cb: CallbackQuery,
    state: FSMContext,
    add_uc: FromDishka[AddChapterUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    text, entities, u16 = await read_buffer(state)
    if not text or u16 == 0:
        await cb.answer("Сначала пришли текст главы.", show_alert=True)
        return
    data = await state.get_data()
    try:
        result = await add_uc(
            AddChapterCommand(
                fic_id=int(data["fic_id"]),
                author_id=cb.from_user.id,
                title=str(data["chapter_title"]),
                text=text,
                entities=entities,
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return

    fic_id = int(data["fic_id"])
    await reset_buffer(state)
    await state.clear()
    await cb.message.answer(
        t("chapter_added", number=result.number, chars=u16),
        reply_markup=build_chapter_or_submit_kb(fic_id),
    )
    await cb.answer()


# ================================================================
# ==============  EDIT META FANFIC (FSM EditFanfic)  =============
# ================================================================


async def _show_edit_menu(
    cb: CallbackQuery,
    *,
    fic_id: int,
    get_uc: GetFanficDraftUseCase,
    tags: ITagRepository,
    reference: IReferenceReader,
) -> None:
    """Отрисовать текущее меню правки с актуальными значениями."""
    if cb.from_user is None or cb.message is None:
        return
    try:
        bundle = await get_uc(
            GetFanficDraftCommand(fic_id=fic_id, author_id=cb.from_user.id)
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    fic = bundle.fic
    fandom = await reference.get_fandom(fic.fandom_id)
    rating = await reference.get_age_rating(int(fic.age_rating_id))
    tag_refs = await tags.list_by_fic(fic.id)

    from html import escape as _h

    text = t(
        "edit_menu",
        title=_h(str(fic.title)),
        fandom=_h(fandom.name) if fandom else "—",
        rating=_h(rating.code) if rating else "—",
        tags=_h(", ".join(str(t_.name) for t_ in tag_refs)) or "—",
        cover="✓" if fic.cover_file_id else "—",
    )
    await cb.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=build_edit_menu_kb(
            fic_id=fic_id, has_cover=fic.cover_file_id is not None
        ),
    )


@router.callback_query(FanficCD.filter(F.action == "edit"))
@inject
async def edit_menu(
    cb: CallbackQuery,
    callback_data: FanficCD,
    state: FSMContext,
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    await state.clear()
    await state.set_state(EditFanficStates.selecting_field)
    await state.update_data(fic_id=callback_data.fic_id)
    await _show_edit_menu(
        cb,
        fic_id=callback_data.fic_id,
        get_uc=get_uc,
        tags=tags_repo,
        reference=reference,
    )
    await cb.answer()


async def _apply_update(
    *,
    cb: CallbackQuery | Message,
    author_id: int,
    fic_id: int,
    get_uc: GetFanficDraftUseCase,
    update_uc: UpdateFanficUseCase,
    tags_repo: ITagRepository,
    overrides: dict[str, Any],
) -> bool:
    """Загружает фик, пересобирает UpdateFanficCommand, подменяя поля из overrides."""
    try:
        bundle = await get_uc(
            GetFanficDraftCommand(fic_id=fic_id, author_id=author_id)
        )
    except DomainError as e:
        await _answer(cb, str(e) or t("error_generic"), alert=True)
        return False
    fic = bundle.fic
    current_tag_names = [str(t_.name) for t_ in await tags_repo.list_by_fic(fic.id)]

    cmd = UpdateFanficCommand(
        fic_id=fic_id,
        author_id=author_id,
        title=overrides.get("title", str(fic.title)),
        summary=overrides.get("summary", str(fic.summary)),
        summary_entities=overrides.get("summary_entities", list(fic.summary_entities)),
        fandom_id=overrides.get("fandom_id", int(fic.fandom_id)),
        age_rating_id=overrides.get("age_rating_id", int(fic.age_rating_id)),
        tag_raws=overrides.get("tag_raws", current_tag_names),
        cover_file_id=overrides.get("cover_file_id", fic.cover_file_id),
        cover_file_unique_id=overrides.get(
            "cover_file_unique_id", fic.cover_file_unique_id
        ),
    )
    try:
        await update_uc(cmd)
    except DomainError as e:
        await _answer(cb, str(e) or t("error_generic"), alert=True)
        return False
    return True


async def _answer(event: CallbackQuery | Message, text: str, *, alert: bool = False) -> None:
    if isinstance(event, CallbackQuery):
        if alert:
            await event.answer(text, show_alert=True)
        elif event.message is not None:
            await event.message.answer(text)
    else:
        await event.answer(text)


# ---------- edit field callbacks ----------


@router.callback_query(EditFieldCD.filter(F.field == "title"))
async def edit_field_title(
    cb: CallbackQuery, callback_data: EditFieldCD, state: FSMContext
) -> None:
    await state.set_state(EditFanficStates.waiting_title)
    await state.update_data(fic_id=callback_data.fic_id)
    if cb.message is not None:
        await cb.message.answer(t("edit_prompt_title"))
    await cb.answer()


@router.message(EditFanficStates.waiting_title)
@inject
async def edit_title_value(
    message: Message,
    state: FSMContext,
    update_uc: FromDishka[UpdateFanficUseCase],
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    if not message.text or message.from_user is None:
        await message.answer(t("fic_expect_text"))
        return
    data = await state.get_data()
    fic_id = int(data["fic_id"])
    ok = await _apply_update(
        cb=message,
        author_id=message.from_user.id,
        fic_id=fic_id,
        get_uc=get_uc,
        update_uc=update_uc,
        tags_repo=tags_repo,
        overrides={"title": message.text},
    )
    if not ok:
        return
    await message.answer(t("edit_done"))
    await state.set_state(EditFanficStates.selecting_field)
    await _send_menu_as_message(message, fic_id, get_uc, tags_repo, reference)


@router.callback_query(EditFieldCD.filter(F.field == "summary"))
async def edit_field_summary(
    cb: CallbackQuery, callback_data: EditFieldCD, state: FSMContext
) -> None:
    await state.set_state(EditFanficStates.waiting_summary)
    await state.update_data(fic_id=callback_data.fic_id)
    if cb.message is not None:
        await cb.message.answer(t("edit_prompt_summary"))
    await cb.answer()


@router.message(EditFanficStates.waiting_summary)
@inject
async def edit_summary_value(
    message: Message,
    state: FSMContext,
    update_uc: FromDishka[UpdateFanficUseCase],
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    if not message.text or message.from_user is None:
        await message.answer(t("fic_expect_text"))
        return
    data = await state.get_data()
    fic_id = int(data["fic_id"])
    entities = _dump_entities(message.entities)
    ok = await _apply_update(
        cb=message,
        author_id=message.from_user.id,
        fic_id=fic_id,
        get_uc=get_uc,
        update_uc=update_uc,
        tags_repo=tags_repo,
        overrides={"summary": message.text, "summary_entities": entities},
    )
    if not ok:
        return
    await message.answer(t("edit_done"))
    await state.set_state(EditFanficStates.selecting_field)
    await _send_menu_as_message(message, fic_id, get_uc, tags_repo, reference)


@router.callback_query(EditFieldCD.filter(F.field == "tags"))
async def edit_field_tags(
    cb: CallbackQuery, callback_data: EditFieldCD, state: FSMContext
) -> None:
    await state.set_state(EditFanficStates.waiting_tags)
    await state.update_data(fic_id=callback_data.fic_id)
    if cb.message is not None:
        await cb.message.answer(t("edit_prompt_tags"))
    await cb.answer()


@router.message(EditFanficStates.waiting_tags)
@inject
async def edit_tags_value(
    message: Message,
    state: FSMContext,
    update_uc: FromDishka[UpdateFanficUseCase],
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    if not message.text or message.from_user is None:
        await message.answer(t("fic_expect_text"))
        return
    data = await state.get_data()
    fic_id = int(data["fic_id"])
    raw = message.text.strip()
    if raw == "-":
        tag_raws: list[str] = []
    else:
        tag_raws = [p.strip() for p in raw.split(",") if p.strip()]
    ok = await _apply_update(
        cb=message,
        author_id=message.from_user.id,
        fic_id=fic_id,
        get_uc=get_uc,
        update_uc=update_uc,
        tags_repo=tags_repo,
        overrides={"tag_raws": tag_raws},
    )
    if not ok:
        return
    await message.answer(t("edit_done"))
    await state.set_state(EditFanficStates.selecting_field)
    await _send_menu_as_message(message, fic_id, get_uc, tags_repo, reference)


@router.callback_query(EditFieldCD.filter(F.field == "fandom"))
@inject
async def edit_field_fandom(
    cb: CallbackQuery,
    callback_data: EditFieldCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    await state.set_state(EditFanficStates.waiting_fandom)
    await state.update_data(fic_id=callback_data.fic_id)
    fandoms, total = await reference.list_fandoms_paginated(
        limit=FANDOM_PAGE_SIZE, offset=0, active_only=True
    )
    if cb.message is not None:
        await cb.message.answer(
            t("edit_prompt_fandom"),
            reply_markup=build_fandom_picker_kb(
                fandoms=fandoms, page=0, total=total
            ),
        )
    await cb.answer()


@router.callback_query(
    EditFanficStates.waiting_fandom, FandomPickCD.filter(F.action == "page")
)
@inject
async def edit_fandom_page(
    cb: CallbackQuery,
    callback_data: FandomPickCD,
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    fandoms, total = await reference.list_fandoms_paginated(
        limit=FANDOM_PAGE_SIZE,
        offset=callback_data.page * FANDOM_PAGE_SIZE,
        active_only=True,
    )
    await cb.message.edit_reply_markup(
        reply_markup=build_fandom_picker_kb(
            fandoms=fandoms, page=callback_data.page, total=total
        )
    )
    await cb.answer()


@router.callback_query(
    EditFanficStates.waiting_fandom, FandomPickCD.filter(F.action == "pick")
)
@inject
async def edit_fandom_pick(
    cb: CallbackQuery,
    callback_data: FandomPickCD,
    state: FSMContext,
    update_uc: FromDishka[UpdateFanficUseCase],
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    data = await state.get_data()
    fic_id = int(data["fic_id"])
    ok = await _apply_update(
        cb=cb,
        author_id=cb.from_user.id,
        fic_id=fic_id,
        get_uc=get_uc,
        update_uc=update_uc,
        tags_repo=tags_repo,
        overrides={"fandom_id": callback_data.fandom_id},
    )
    if not ok:
        return
    if cb.message is not None:
        await cb.message.answer(t("edit_done"))
    await state.set_state(EditFanficStates.selecting_field)
    await _show_edit_menu(
        cb, fic_id=fic_id, get_uc=get_uc, tags=tags_repo, reference=reference
    )
    await cb.answer()


@router.callback_query(EditFieldCD.filter(F.field == "age_rating"))
@inject
async def edit_field_age_rating(
    cb: CallbackQuery,
    callback_data: EditFieldCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    await state.set_state(EditFanficStates.waiting_age_rating)
    await state.update_data(fic_id=callback_data.fic_id)
    ratings = await reference.list_age_ratings()
    if cb.message is not None:
        await cb.message.answer(
            t("fic_create_age_rating_prompt"),
            reply_markup=build_age_rating_kb(ratings),
        )
    await cb.answer()


@router.callback_query(EditFanficStates.waiting_age_rating, AgeRatingCD.filter())
@inject
async def edit_age_rating_pick(
    cb: CallbackQuery,
    callback_data: AgeRatingCD,
    state: FSMContext,
    update_uc: FromDishka[UpdateFanficUseCase],
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    data = await state.get_data()
    fic_id = int(data["fic_id"])
    ok = await _apply_update(
        cb=cb,
        author_id=cb.from_user.id,
        fic_id=fic_id,
        get_uc=get_uc,
        update_uc=update_uc,
        tags_repo=tags_repo,
        overrides={"age_rating_id": callback_data.rating_id},
    )
    if not ok:
        return
    if cb.message is not None:
        await cb.message.answer(t("edit_done"))
    await state.set_state(EditFanficStates.selecting_field)
    await _show_edit_menu(
        cb, fic_id=fic_id, get_uc=get_uc, tags=tags_repo, reference=reference
    )
    await cb.answer()


@router.callback_query(EditFieldCD.filter(F.field == "cover"))
async def edit_field_cover(
    cb: CallbackQuery, callback_data: EditFieldCD, state: FSMContext
) -> None:
    await state.set_state(EditFanficStates.waiting_cover)
    await state.update_data(fic_id=callback_data.fic_id)
    if cb.message is not None:
        await cb.message.answer(t("edit_prompt_cover"))
    await cb.answer()


@router.message(EditFanficStates.waiting_cover, F.photo)
@inject
async def edit_cover_value(
    message: Message,
    state: FSMContext,
    update_uc: FromDishka[UpdateFanficUseCase],
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    if message.from_user is None or not message.photo:
        await message.answer(t("fic_expect_photo"))
        return
    photo = message.photo[-1]
    data = await state.get_data()
    fic_id = int(data["fic_id"])
    ok = await _apply_update(
        cb=message,
        author_id=message.from_user.id,
        fic_id=fic_id,
        get_uc=get_uc,
        update_uc=update_uc,
        tags_repo=tags_repo,
        overrides={
            "cover_file_id": photo.file_id,
            "cover_file_unique_id": photo.file_unique_id,
        },
    )
    if not ok:
        return
    await message.answer(t("edit_done"))
    await state.set_state(EditFanficStates.selecting_field)
    await _send_menu_as_message(message, fic_id, get_uc, tags_repo, reference)


@router.message(EditFanficStates.waiting_cover)
async def edit_cover_bad(message: Message) -> None:
    await message.answer(t("fic_expect_photo"))


@router.callback_query(EditFieldCD.filter(F.field == "cover_clear"))
@inject
async def edit_cover_clear(
    cb: CallbackQuery,
    callback_data: EditFieldCD,
    state: FSMContext,
    update_uc: FromDishka[UpdateFanficUseCase],
    get_uc: FromDishka[GetFanficDraftUseCase],
    tags_repo: FromDishka[ITagRepository],
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    fic_id = callback_data.fic_id
    ok = await _apply_update(
        cb=cb,
        author_id=cb.from_user.id,
        fic_id=fic_id,
        get_uc=get_uc,
        update_uc=update_uc,
        tags_repo=tags_repo,
        overrides={"cover_file_id": None, "cover_file_unique_id": None},
    )
    if not ok:
        return
    if cb.message is not None:
        await cb.message.answer(t("edit_cover_cleared"))
    await state.set_state(EditFanficStates.selecting_field)
    await _show_edit_menu(
        cb, fic_id=fic_id, get_uc=get_uc, tags=tags_repo, reference=reference
    )
    await cb.answer()


async def _send_menu_as_message(
    message: Message,
    fic_id: int,
    get_uc: GetFanficDraftUseCase,
    tags_repo: ITagRepository,
    reference: IReferenceReader,
) -> None:
    """Отправить меню правки после ввода текста (нет CallbackQuery)."""
    if message.from_user is None:
        return
    try:
        bundle = await get_uc(
            GetFanficDraftCommand(fic_id=fic_id, author_id=message.from_user.id)
        )
    except DomainError:
        return
    fic = bundle.fic
    fandom = await reference.get_fandom(fic.fandom_id)
    rating = await reference.get_age_rating(int(fic.age_rating_id))
    tag_refs = await tags_repo.list_by_fic(fic.id)
    from html import escape as _h

    await message.answer(
        t(
            "edit_menu",
            title=_h(str(fic.title)),
            fandom=_h(fandom.name) if fandom else "—",
            rating=_h(rating.code) if rating else "—",
            tags=_h(", ".join(str(t_.name) for t_ in tag_refs)) or "—",
            cover="✓" if fic.cover_file_id else "—",
        ),
        parse_mode="HTML",
        reply_markup=build_edit_menu_kb(
            fic_id=fic_id, has_cover=fic.cover_file_id is not None
        ),
    )


# ================================================================
# ==============  CHAPTERS MANAGEMENT  ===========================
# ================================================================


@router.callback_query(FanficCD.filter(F.action == "chapters"))
@inject
async def chapters_list(
    cb: CallbackQuery,
    callback_data: FanficCD,
    get_uc: FromDishka[GetFanficDraftUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        bundle = await get_uc(
            GetFanficDraftCommand(
                fic_id=callback_data.fic_id, author_id=cb.from_user.id
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    if not bundle.chapters:
        await cb.message.answer(t("chapters_list_empty"))
        await cb.answer()
        return
    from html import escape as _h

    editable = bundle.fic.status in (
        FicStatus.DRAFT,
        FicStatus.REJECTED,
        FicStatus.REVISING,
    )
    await cb.message.answer(
        t(
            "chapters_list_header",
            title=_h(str(bundle.fic.title)),
            count=len(bundle.chapters),
        ),
        parse_mode="HTML",
        reply_markup=build_chapter_list_kb(
            fic_id=int(bundle.fic.id),
            chapters=bundle.chapters,
            editable=editable,
        ),
    )
    await cb.answer()


@router.callback_query(ChapterListCD.filter())
@inject
async def chapter_card(
    cb: CallbackQuery,
    callback_data: ChapterListCD,
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    ch = await chapters_repo.get(ChapterId(callback_data.chapter_id))
    if ch is None:
        await cb.answer("Глава не найдена.", show_alert=True)
        return
    from html import escape as _h

    await cb.message.answer(
        t(
            "chapter_card",
            number=int(ch.number),
            title=_h(str(ch.title)),
            status=ch.status.value,
            chars=int(ch.chars_count),
        ),
        parse_mode="HTML",
        reply_markup=build_chapter_actions_kb(
            fic_id=callback_data.fic_id,
            chapter_id=int(ch.id),
            status=ch.status,
        ),
    )
    await cb.answer()


# ---------- edit chapter flow ----------


@router.callback_query(ChapterActionCD.filter(F.action == "edit"))
@inject
async def chapter_edit_start(
    cb: CallbackQuery,
    callback_data: ChapterActionCD,
    state: FSMContext,
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    ch = await chapters_repo.get(ChapterId(callback_data.chapter_id))
    if ch is None:
        await cb.answer("Глава не найдена.", show_alert=True)
        return
    if ch.status not in (FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING):
        await cb.answer(
            "Редактировать можно только главы в статусе draft/rejected/revising.",
            show_alert=True,
        )
        return
    await state.clear()
    await state.set_state(EditChapterStates.waiting_title)
    await state.update_data(
        chapter_id=int(ch.id), fic_id=int(ch.fic_id)
    )
    if cb.message is not None:
        await cb.message.answer(t("chapter_edit_title_prompt"))
    await cb.answer()


@router.message(EditChapterStates.waiting_title)
async def chapter_edit_title(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer(t("fic_expect_text"))
        return
    await state.update_data(chapter_title=message.text)
    await reset_buffer(state)
    await state.set_state(EditChapterStates.waiting_text)
    await message.answer(t("chapter_edit_text_prompt"))


@router.message(EditChapterStates.waiting_text, F.text)
@inject
async def chapter_edit_text_chunk(
    message: Message,
    state: FSMContext,
    settings: FromDishka[Settings],
) -> None:
    if not message.text or message.from_user is None:
        await message.answer(t("fic_expect_text"))
        return
    u16, overflow = await append_chunk(state, message, max_chars=settings.max_chapter_chars)
    if overflow:
        await message.answer(
            t("chapter_overflow", limit=settings.max_chapter_chars),
            reply_markup=build_chapter_compose_kb(
                u16=(await read_buffer(state))[2], limit=settings.max_chapter_chars
            ),
        )
        return
    await message.answer(
        t("chapter_chunk_added", u16=u16, limit=settings.max_chapter_chars),
        reply_markup=build_chapter_compose_kb(u16=u16, limit=settings.max_chapter_chars),
    )


@router.callback_query(EditChapterStates.waiting_text, F.data == "chapter:cancel")
async def chapter_edit_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await reset_buffer(state)
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(t("chapter_discarded"))
    await cb.answer()


@router.callback_query(EditChapterStates.waiting_text, F.data == "chapter:finish")
@inject
async def chapter_edit_finish(
    cb: CallbackQuery,
    state: FSMContext,
    update_chapter_uc: FromDishka[UpdateChapterUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    text, entities, u16 = await read_buffer(state)
    if not text or u16 == 0:
        await cb.answer("Сначала пришли текст главы.", show_alert=True)
        return
    data = await state.get_data()
    try:
        await update_chapter_uc(
            UpdateChapterCommand(
                chapter_id=int(data["chapter_id"]),
                author_id=cb.from_user.id,
                title=str(data["chapter_title"]),
                text=text,
                entities=entities,
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return

    fic_id = int(data["fic_id"])
    await reset_buffer(state)
    await state.clear()
    await cb.message.answer(
        t("chapter_updated_msg", u16=u16),
        reply_markup=build_chapter_or_submit_kb(fic_id),
    )
    await cb.answer()


# ---------- delete chapter ----------


@router.callback_query(ChapterActionCD.filter(F.action == "delete"))
@inject
async def chapter_delete_prompt(
    cb: CallbackQuery,
    callback_data: ChapterActionCD,
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    ch = await chapters_repo.get(ChapterId(callback_data.chapter_id))
    if ch is None:
        await cb.answer("Глава не найдена.", show_alert=True)
        return
    if ch.status != FicStatus.DRAFT:
        await cb.answer(
            "Удалять можно только главы-черновики. Отмени подачу или доработай.",
            show_alert=True,
        )
        return
    from html import escape as _h

    if cb.message is not None:
        await cb.message.answer(
            t(
                "chapter_delete_confirm",
                number=int(ch.number),
                title=_h(str(ch.title)),
            ),
            parse_mode="HTML",
            reply_markup=build_delete_confirm_kb(
                chapter_id=int(ch.id), fic_id=int(ch.fic_id)
            ),
        )
    await cb.answer()


@router.callback_query(ChapterActionCD.filter(F.action == "confirm_delete"))
@inject
async def chapter_delete_confirm(
    cb: CallbackQuery,
    callback_data: ChapterActionCD,
    delete_uc: FromDishka[DeleteDraftChapterUseCase],
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    ch = await chapters_repo.get(ChapterId(callback_data.chapter_id))
    if ch is None:
        await cb.answer("Глава не найдена.", show_alert=True)
        return
    fic_id = int(ch.fic_id)
    try:
        await delete_uc(
            DeleteDraftChapterCommand(
                chapter_id=callback_data.chapter_id, author_id=cb.from_user.id
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return
    if cb.message is not None:
        await cb.message.answer(
            t("chapter_deleted"),
            reply_markup=build_fanfic_card_kb(fic_id, FicStatus.DRAFT),
        )
    await cb.answer()


@router.callback_query(ChapterActionCD.filter(F.action == "cancel_delete"))
async def chapter_delete_cancel(
    cb: CallbackQuery, callback_data: ChapterActionCD
) -> None:
    if cb.message is not None:
        await cb.message.answer(t("chapter_delete_cancelled"))
    await cb.answer()
