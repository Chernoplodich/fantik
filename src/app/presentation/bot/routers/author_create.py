"""Мастер создания нового фика.

FSM: Title → Summary → Fandom → AgeRating → Tags → Cover → ChapterOrSubmit →
    WaitingChapterTitle → WaitingChapterText → (назад в ChapterOrSubmit).

Meta (title/summary/tags/fandom/rating/cover) хранятся в FSM data до первого
add_chapter. Fanfic создаётся в БД в момент первого добавления главы — тексты
глав живут в `chapters` со status=draft, даже если FSM позже протухнет.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize
from dishka.integrations.aiogram import FromDishka, inject

from app.application.fanfics.add_chapter import (
    AddChapterCommand,
    AddChapterUseCase,
)
from app.application.fanfics.create_draft import (
    CreateDraftCommand,
    CreateDraftUseCase,
)
from app.application.fanfics.ports import IReferenceReader
from app.application.reference.proposals import (
    SubmitFandomProposalCommand,
    SubmitFandomProposalUseCase,
)
from app.core.config import Settings
from app.core.errors import DomainError, ValidationError
from app.domain.fanfics.value_objects import (
    MAX_TAGS_PER_FIC,
    ChapterTitle,
    FanficTitle,
    Summary,
    TagName,
)
from app.presentation.bot.callback_data.fanfic import (
    AgeRatingCD,
    FandomPickCD,
    FandomProposeCategoryCD,
    FanficCD,
)
from app.presentation.bot.fandom_categories import category_long_label
from app.presentation.bot.fsm.states.create_fanfic import CreateFanficStates
from app.presentation.bot.keyboards.create_fanfic import (
    build_age_rating_kb,
    build_cancel_kb,
    build_chapter_or_submit_kb,
    build_cover_kb,
)
from app.presentation.bot.keyboards.fandom_picker import (
    FANDOMS_PER_PAGE as PICKER_PAGE_SIZE,
)
from app.presentation.bot.keyboards.fandom_picker import (
    build_categories_kb,
    build_fandoms_in_category_kb,
    build_propose_categories_kb,
    build_search_results_kb,
)
from app.presentation.bot.routers._chapter_buffer import (
    append_chunk,
    build_chapter_compose_kb,
    read_buffer,
    reset_buffer,
)
from app.presentation.bot.texts.ru import t

router = Router(name="author_create")


# ---------- entry ----------


@router.message(Command("new_fic"))
@router.callback_query(F.data == "menu:new_fic")
async def start_create(
    event: Message | CallbackQuery,
    state: FSMContext,
) -> None:
    # HasAuthorNick используем позже в handler'е — для упрощения проверим здесь
    # через общий флоу. Основной фильтр нужно вешать; а если пользователь
    # не автор, поможем ему: сразу скажем.
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message is not None:
            await event.message.answer(t("fic_create_title_prompt"), reply_markup=build_cancel_kb())
    else:
        await event.answer(t("fic_create_title_prompt"), reply_markup=build_cancel_kb())
    await state.set_state(CreateFanficStates.waiting_title)
    await state.update_data(
        title=None,
        summary=None,
        summary_entities=[],
        fandom_id=None,
        age_rating_id=None,
        tag_raws=[],
        cover_file_id=None,
        cover_file_unique_id=None,
        fic_id=None,
        chapter_title=None,
    )


# ---------- cancel ----------


@router.callback_query(F.data == "fic_create:cancel")
async def cancel_create(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(t("fic_create_cancelled"))
    await cb.answer()


# ---------- title ----------


@router.message(CreateFanficStates.waiting_title)
async def on_title(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer(t("fic_expect_text"))
        return
    try:
        title = FanficTitle(message.text)
    except ValidationError as e:
        await message.answer(str(e), reply_markup=build_cancel_kb())
        return
    await state.update_data(title=str(title))
    await state.set_state(CreateFanficStates.waiting_summary)
    await message.answer(t("fic_create_summary_prompt"), reply_markup=build_cancel_kb())


# ---------- summary ----------


@router.message(CreateFanficStates.waiting_summary)
@inject
async def on_summary(
    message: Message,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    if not message.text:
        await message.answer(t("fic_expect_text"))
        return
    try:
        summary = Summary(message.text)
    except ValidationError as e:
        await message.answer(str(e), reply_markup=build_cancel_kb())
        return
    entities = _dump_entities(message.entities)
    await state.update_data(summary=str(summary), summary_entities=entities)
    await _prompt_fandom_page(message, state, reference, page=0)


async def _prompt_fandom_page(
    message: Message,
    state: FSMContext,
    reference: IReferenceReader,  # noqa: ARG001 — оставлен для обратной совместимости
    *,
    page: int,  # noqa: ARG001
) -> None:
    """Открыть корень пикера фандомов (двухступенчатый: категория → список)."""
    await state.set_state(CreateFanficStates.waiting_fandom)
    kb = build_categories_kb(flow="create", show_propose=True)
    await message.answer(
        t("fic_create_fandom_prompt"),
        reply_markup=kb,
        parse_mode="HTML",
    )


# ---------- fandom: navigation (cats / cat / search / propose) ----------


@router.callback_query(
    CreateFanficStates.waiting_fandom,
    FandomPickCD.filter(F.action == "cats"),
)
async def on_fandom_back_to_cats(cb: CallbackQuery) -> None:
    if cb.message is None:
        await cb.answer()
        return
    kb = build_categories_kb(flow="create", show_propose=True)
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            t("fic_create_fandom_prompt"),
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        await cb.message.answer(t("fic_create_fandom_prompt"), reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(
    CreateFanficStates.waiting_fandom,
    FandomPickCD.filter(F.action == "cat"),
)
@inject
async def on_fandom_pick_category(
    cb: CallbackQuery,
    callback_data: FandomPickCD,
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    cat = (callback_data.cat or "other").lower()
    page = max(0, callback_data.page)
    fandoms, total = await reference.list_fandoms_by_category(
        category=cat,
        limit=PICKER_PAGE_SIZE,
        offset=page * PICKER_PAGE_SIZE,
        active_only=True,
    )
    has_more = (page + 1) * PICKER_PAGE_SIZE < total
    kb = build_fandoms_in_category_kb(
        flow="create",
        cat=cat,
        fandoms=fandoms,
        page=page,
        has_more=has_more,
    )
    body = f"<b>{category_long_label(cat)}</b>\n\nВыбери фандом или нажми «🔍 Найти по названию»."
    if not fandoms:
        body = (
            f"<b>{category_long_label(cat)}</b>\n\n"
            "Пока пусто. Попробуй другую категорию или предложи новый фандом."
        )
    try:
        await cb.message.edit_text(body, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        await cb.message.answer(body, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(
    CreateFanficStates.waiting_fandom,
    FandomPickCD.filter(F.action == "search"),
)
async def on_fandom_search_start(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(CreateFanficStates.waiting_fandom_search)
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            t("fic_create_fandom_search_prompt"), parse_mode="HTML"
        )
    except Exception:  # noqa: BLE001
        await cb.message.answer(t("fic_create_fandom_search_prompt"), parse_mode="HTML")
    await cb.answer()


@router.message(CreateFanficStates.waiting_fandom_search, F.text)
@inject
async def on_fandom_search_text(
    message: Message,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    raw = (message.text or "").strip()
    # Команды (/start, /help, /catalog) — пропускаем и сбрасываем state, чтобы
    # пользователь мог выйти из мастера в любой момент. cmd_start первым перехватит,
    # этот guard — страховка.
    if raw.startswith("/"):
        await state.clear()
        return
    if len(raw) < 2:
        await message.answer(t("fic_create_fandom_search_too_short"))
        return
    try:
        fandoms = await reference.search_fandoms(query=raw, limit=20, active_only=True)
    except Exception:  # noqa: BLE001
        from app.core.logging import get_logger

        get_logger(__name__).exception("fandom_search_failed", q=raw)
        await message.answer(
            "Не получилось выполнить поиск. Попробуй ещё раз или вернись к категориям."
        )
        return
    await state.set_state(CreateFanficStates.waiting_fandom)
    if not fandoms:
        kb = build_categories_kb(flow="create", show_propose=True)
        await message.answer(
            t("fic_create_fandom_search_no_results", q=raw),
            reply_markup=kb,
        )
        return
    kb = build_search_results_kb(flow="create", fandoms=fandoms)
    await message.answer(f"По запросу «{raw}»:", reply_markup=kb)


@router.callback_query(
    CreateFanficStates.waiting_fandom,
    FandomPickCD.filter(F.action == "propose"),
)
async def on_fandom_propose_start(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(CreateFanficStates.waiting_fandom_proposal_name)
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            t("fic_create_fandom_propose_name_prompt"),
            reply_markup=build_cancel_kb(),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        await cb.message.answer(
            t("fic_create_fandom_propose_name_prompt"),
            reply_markup=build_cancel_kb(),
            parse_mode="HTML",
        )
    await cb.answer()


@router.message(CreateFanficStates.waiting_fandom_proposal_name, F.text)
async def on_fandom_propose_name(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await state.clear()
        return
    if not raw or len(raw) > 256:
        await message.answer("Название фандома: 1–256 символов. Попробуй ещё раз.")
        return
    await state.update_data(_proposal_name=raw)
    await state.set_state(CreateFanficStates.waiting_fandom_proposal_category)
    await message.answer(
        t("fic_create_fandom_propose_category_prompt"),
        reply_markup=build_propose_categories_kb(),
        parse_mode="HTML",
    )


@router.callback_query(
    CreateFanficStates.waiting_fandom_proposal_category,
    FandomProposeCategoryCD.filter(),
)
@inject
async def on_fandom_propose_category(
    cb: CallbackQuery,
    callback_data: FandomProposeCategoryCD,
    state: FSMContext,
    submit_uc: FromDishka[SubmitFandomProposalUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    data = await state.get_data()
    name = str(data.get("_proposal_name") or "").strip()
    if not name:
        await cb.answer("Сначала пришли название.", show_alert=True)
        return
    try:
        result = await submit_uc(
            SubmitFandomProposalCommand(
                requested_by=cb.from_user.id,
                name=name,
                category_hint=callback_data.cat,
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return

    msg = (
        t("fic_create_fandom_propose_done")
        if result.created
        else t("fic_create_fandom_propose_duplicate")
    )

    # Возвращаем юзера в выбор фандома (категории) — пусть выберет существующий
    # и продолжит создание работы.
    await state.set_state(CreateFanficStates.waiting_fandom)
    kb = build_categories_kb(flow="create", show_propose=True)
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            msg + "\n\n" + t("fic_create_fandom_prompt"),
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001
        await cb.message.answer(
            msg + "\n\n" + t("fic_create_fandom_prompt"),
            reply_markup=kb,
            parse_mode="HTML",
        )
    await cb.answer()


@router.callback_query(
    CreateFanficStates.waiting_fandom,
    FandomPickCD.filter(F.action == "pick"),
)
@inject
async def on_fandom_pick(
    cb: CallbackQuery,
    callback_data: FandomPickCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    await state.update_data(fandom_id=callback_data.fandom_id)
    ratings = await reference.list_age_ratings()
    await state.set_state(CreateFanficStates.waiting_age_rating)
    if cb.message is not None:
        await cb.message.answer(
            t("fic_create_age_rating_prompt"),
            reply_markup=build_age_rating_kb(ratings),
        )
    await cb.answer()


# ---------- age rating ----------


@router.callback_query(CreateFanficStates.waiting_age_rating, AgeRatingCD.filter())
async def on_rating(
    cb: CallbackQuery,
    callback_data: AgeRatingCD,
    state: FSMContext,
) -> None:
    await state.update_data(age_rating_id=callback_data.rating_id)
    await state.set_state(CreateFanficStates.waiting_tags)
    if cb.message is not None:
        await cb.message.answer(t("fic_create_tags_prompt"), reply_markup=build_cancel_kb())
    await cb.answer()


# ---------- tags ----------


@router.message(CreateFanficStates.waiting_tags)
async def on_tags(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer(t("fic_expect_text"))
        return
    raw = message.text.strip()
    if raw == "-":
        tag_raws: list[str] = []
    else:
        tag_raws = [p.strip() for p in raw.split(",") if p.strip()]
    if len(tag_raws) > MAX_TAGS_PER_FIC:
        await message.answer(
            f"Слишком много тегов: {len(tag_raws)}. Максимум — {MAX_TAGS_PER_FIC}.",
            reply_markup=build_cancel_kb(),
        )
        return
    for raw_tag in tag_raws:
        try:
            TagName(raw_tag)
        except ValidationError as e:
            await message.answer(f"Тег «{raw_tag[:50]}»: {e}", reply_markup=build_cancel_kb())
            return
    await state.update_data(tag_raws=tag_raws)
    await state.set_state(CreateFanficStates.waiting_cover)
    await message.answer(t("fic_create_cover_prompt"), reply_markup=build_cover_kb())


# ---------- cover ----------


@router.message(CreateFanficStates.waiting_cover, F.photo)
@inject
async def on_cover(
    message: Message,
    state: FSMContext,
    bot: FromDishka[Bot],
    settings: FromDishka[Settings],
) -> None:
    photo: PhotoSize = (message.photo or [])[-1]  # type: ignore[index]
    from app.infrastructure.telegram.cover_validator import (
        CoverError,
        validate_cover,
    )

    res = await validate_cover(bot, photo.file_id, max_size_bytes=settings.cover_max_size_bytes)
    if not res.ok:
        if res.error is CoverError.TOO_LARGE:
            max_mb = settings.cover_max_size_bytes // (1024 * 1024)
            await message.answer(
                f"Обложка слишком большая (>{max_mb} МБ). Сожми или загрузи другую."
            )
        elif res.error is CoverError.BAD_FORMAT:
            await message.answer(
                "Поддерживаются только обложки в формате JPEG или PNG. Загрузи другую."
            )
        else:
            await message.answer("Не получилось обработать обложку. Попробуй ещё раз.")
        return

    await state.update_data(
        cover_file_id=photo.file_id,
        cover_file_unique_id=photo.file_unique_id,
    )
    await _prompt_chapter_or_submit(message, state)


@router.callback_query(CreateFanficStates.waiting_cover, F.data == "fic_create:skip_cover")
async def on_cover_skip(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is not None:
        await _prompt_chapter_or_submit(cb.message, state)
    await cb.answer()


@router.message(CreateFanficStates.waiting_cover)
async def on_cover_expect_photo(message: Message) -> None:
    await message.answer(t("fic_expect_photo"), reply_markup=build_cover_kb())


async def _prompt_chapter_or_submit(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(CreateFanficStates.chapter_or_submit)
    fic_id = data.get("fic_id") or 0
    await message.answer(
        t("fic_create_chapter_or_submit", fic_id=fic_id or "—"),
        reply_markup=_placeholder_kb_before_first_chapter()
        if not fic_id
        else build_chapter_or_submit_kb(int(fic_id)),
    )


def _placeholder_kb_before_first_chapter() -> Any:
    """До первого add_chapter у нас нет fic_id. Показываем минимальную клавиатуру."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить первую главу", callback_data="fic_create:first_chapter")
    b.button(text="Отмена", callback_data="fic_create:cancel")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(CreateFanficStates.chapter_or_submit, F.data == "fic_create:first_chapter")
async def on_first_chapter(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateFanficStates.waiting_chapter_title)
    if cb.message is not None:
        await cb.message.answer(t("fic_create_chapter_title_prompt"))
    await cb.answer()


@router.callback_query(
    CreateFanficStates.chapter_or_submit,
    FanficCD.filter(F.action == "add_chapter"),
)
async def on_add_chapter_btn(cb: CallbackQuery, callback_data: FanficCD, state: FSMContext) -> None:
    await state.update_data(fic_id=callback_data.fic_id)
    await state.set_state(CreateFanficStates.waiting_chapter_title)
    if cb.message is not None:
        await cb.message.answer(t("fic_create_chapter_title_prompt"))
    await cb.answer()


# ---------- chapter title ----------


@router.message(CreateFanficStates.waiting_chapter_title)
async def on_chapter_title(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer(t("fic_expect_text"))
        return
    try:
        ch_title = ChapterTitle(message.text)
    except ValidationError as e:
        await message.answer(str(e))
        return
    await state.update_data(chapter_title=str(ch_title))
    await reset_buffer(state)
    await state.set_state(CreateFanficStates.waiting_chapter_text)
    await message.answer(t("fic_create_chapter_text_prompt", max_chars=100_000))


# ---------- chapter text (буферизация нескольких сообщений) ----------


@router.message(CreateFanficStates.waiting_chapter_text, F.text)
@inject
async def on_chapter_text_chunk(
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
                u16=(await read_buffer(state))[2],
                limit=settings.max_chapter_chars,
            ),
        )
        return
    await message.answer(
        t("chapter_chunk_added", u16=u16, limit=settings.max_chapter_chars),
        reply_markup=build_chapter_compose_kb(u16=u16, limit=settings.max_chapter_chars),
    )


@router.message(CreateFanficStates.waiting_chapter_text)
async def on_chapter_text_bad(message: Message) -> None:
    await message.answer(t("fic_expect_text"))


@router.callback_query(CreateFanficStates.waiting_chapter_text, F.data == "chapter:cancel")
async def on_chapter_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await reset_buffer(state)
    data = await state.get_data()
    fic_id = data.get("fic_id")
    await state.set_state(CreateFanficStates.chapter_or_submit)
    if cb.message is not None:
        if fic_id:
            await cb.message.answer(
                t("chapter_discarded"),
                reply_markup=build_chapter_or_submit_kb(int(fic_id)),
            )
        else:
            await cb.message.answer(
                t("chapter_discarded"),
                reply_markup=_placeholder_kb_before_first_chapter(),
            )
    await cb.answer()


@router.callback_query(CreateFanficStates.waiting_chapter_text, F.data == "chapter:finish")
@inject
async def on_chapter_finish(
    cb: CallbackQuery,
    state: FSMContext,
    create_uc: FromDishka[CreateDraftUseCase],
    add_chapter_uc: FromDishka[AddChapterUseCase],
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
        fic_id = data.get("fic_id")
        if not fic_id:
            draft = await create_uc(
                CreateDraftCommand(
                    author_id=cb.from_user.id,
                    title=str(data["title"]),
                    summary=str(data["summary"]),
                    summary_entities=list(data.get("summary_entities") or []),
                    fandom_id=int(data["fandom_id"]),
                    age_rating_id=int(data["age_rating_id"]),
                    tag_raws=list(data.get("tag_raws") or []),
                    cover_file_id=data.get("cover_file_id"),
                    cover_file_unique_id=data.get("cover_file_unique_id"),
                )
            )
            fic_id = draft.fic_id
            await state.update_data(fic_id=fic_id)

        result = await add_chapter_uc(
            AddChapterCommand(
                fic_id=int(fic_id),
                author_id=cb.from_user.id,
                title=str(data["chapter_title"]),
                text=text,
                entities=entities,
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or t("error_generic"), show_alert=True)
        return

    await reset_buffer(state)
    await state.set_state(CreateFanficStates.chapter_or_submit)
    await cb.message.answer(
        t("chapter_added", number=result.number, chars=u16),
        reply_markup=build_chapter_or_submit_kb(int(fic_id)),
    )
    await cb.answer()


# ---------- helpers ----------


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
