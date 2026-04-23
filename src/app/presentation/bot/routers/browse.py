"""Каталог: /catalog + ленты «Новое» / «Топ» / «По фэндому» + поиск с фильтрами."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.fanfics.ports import IReferenceReader
from app.application.reading.list_feed import (
    FeedKind,
    ListFeedCommand,
    ListFeedUseCase,
)
from app.application.search.dto import SearchCommand, SortMode
from app.application.search.ports import ISuggestReader
from app.application.search.search import SearchUseCase
from app.core.logging import get_logger
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.browse import BrowseCD
from app.presentation.bot.callback_data.search import SearchCD
from app.presentation.bot.fsm.states.search import SearchFiltersFSM
from app.presentation.bot.keyboards.browse import (
    browse_root_kb,
    fandom_pick_kb,
)
from app.presentation.bot.keyboards.reader import feed_kb
from app.presentation.bot.keyboards.search_filters import (
    age_rating_picker_kb,
    filters_root_kb,
    results_kb,
    sort_picker_kb,
    tag_picker_kb,
)
from app.presentation.bot.keyboards.search_filters import (
    fandom_picker_kb as search_fandom_picker_kb,
)

log = get_logger(__name__)
router = Router(name="browse")

_PAGE_SIZE = 10
_FANDOMS_PER_PAGE = 12
_SEARCH_FANDOMS_PER_PAGE = 8
_POPULAR_TAGS_COUNT = 24
_DEFAULT_SORT: SortMode = "relevance"


# ---------- root ----------


@router.message(Command("catalog"))
async def cmd_catalog(message: Message) -> None:
    await message.answer("📚 Каталог работ", reply_markup=browse_root_kb())


@router.callback_query(F.data == "menu:browse")
@router.callback_query(BrowseCD.filter(F.a == "root"))
async def show_root(cb: CallbackQuery) -> None:
    if cb.message is None:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            "📚 Каталог работ", reply_markup=browse_root_kb()
        )
    except Exception:
        await cb.message.answer("📚 Каталог работ", reply_markup=browse_root_kb())
    await cb.answer()


# ---------- feed: new / top ----------


async def _render_feed(
    cb: CallbackQuery,
    kind: FeedKind,
    fandom_id: int,
    page: int,
    list_feed: ListFeedUseCase,
    reference: IReferenceReader,
) -> None:
    items = await list_feed(
        ListFeedCommand(
            kind=kind,
            fandom_id=fandom_id or None,
            limit=_PAGE_SIZE,
            offset=page * _PAGE_SIZE,
        )
    )
    # has_more оцениваем по полноте страницы (эвристика; точный total — в Этапе 4).
    has_more = len(items) == _PAGE_SIZE

    header_parts: list[str] = []
    header_parts.append("🆕 Новое" if kind == FeedKind.NEW else "🔥 Топ")
    if fandom_id:
        fandom = await reference.get_fandom(FandomId(fandom_id))
        if fandom is not None:
            header_parts.append(f"· {fandom.name}")
    header = " ".join(header_parts)

    if not items:
        body = f"{header}\n\nПока нет работ."
    else:
        lines = [header, ""]
        for idx, it in enumerate(items, start=page * _PAGE_SIZE + 1):
            author = f" — {it.author_nick}" if it.author_nick else ""
            lines.append(
                f"{idx}. {it.title}{author} · ❤️ {it.likes_count} · 📖 {it.chapters_count} гл."
            )
        body = "\n".join(lines)

    kb = feed_kb(
        items=items,
        kind=kind.value,
        fandom_id=fandom_id,
        page=page,
        has_more=has_more,
    )
    if cb.message is not None:
        try:
            await cb.message.edit_text(body, reply_markup=kb)  # type: ignore[union-attr]
        except Exception:
            await cb.message.answer(body, reply_markup=kb)


@router.callback_query(BrowseCD.filter(F.a == "new"))
@inject
async def show_new(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    list_feed: FromDishka[ListFeedUseCase],
    reference: FromDishka[IReferenceReader],
) -> None:
    await _render_feed(cb, FeedKind.NEW, callback_data.fd, callback_data.pg, list_feed, reference)
    await cb.answer()


@router.callback_query(BrowseCD.filter(F.a == "top"))
@inject
async def show_top(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    list_feed: FromDishka[ListFeedUseCase],
    reference: FromDishka[IReferenceReader],
) -> None:
    await _render_feed(cb, FeedKind.TOP, callback_data.fd, callback_data.pg, list_feed, reference)
    await cb.answer()


# ---------- by_fandom: pick → feed ----------


@router.callback_query(BrowseCD.filter(F.a == "by_fandom"))
@router.callback_query(BrowseCD.filter(F.a == "fd_page"))
@inject
async def pick_fandom(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    reference: FromDishka[IReferenceReader],
) -> None:
    page = callback_data.pg
    fandoms, total = await reference.list_fandoms_paginated(
        limit=_FANDOMS_PER_PAGE, offset=page * _FANDOMS_PER_PAGE, active_only=True
    )
    has_more = (page + 1) * _FANDOMS_PER_PAGE < total
    if cb.message is not None:
        try:
            await cb.message.edit_text(  # type: ignore[union-attr]
                "🏷 Выбери фэндом:",
                reply_markup=fandom_pick_kb(fandoms=fandoms, page=page, has_more=has_more),
            )
        except Exception:
            await cb.message.answer(
                "🏷 Выбери фэндом:",
                reply_markup=fandom_pick_kb(fandoms=fandoms, page=page, has_more=has_more),
            )
    await cb.answer()


@router.callback_query(BrowseCD.filter(F.a == "fandom"))
@inject
async def show_fandom_feed(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    list_feed: FromDishka[ListFeedUseCase],
    reference: FromDishka[IReferenceReader],
) -> None:
    await _render_feed(cb, FeedKind.NEW, callback_data.fd, callback_data.pg, list_feed, reference)
    await cb.answer()


# ================================================================
#                       Поиск с фильтрами
# ================================================================


async def _get_search_state(state: FSMContext) -> dict[str, object]:
    """Считать состояние поиска из FSM-data c дефолтами."""
    data = await state.get_data()
    return {
        "fandoms": list(data.get("s_fandoms") or []),
        "ages": list(data.get("s_ages") or []),
        "tags": list(data.get("s_tags") or []),
        "sort": str(data.get("s_sort") or _DEFAULT_SORT),
    }


async def _save_search_state(state: FSMContext, s: dict[str, object]) -> None:
    await state.update_data(
        s_fandoms=list(s["fandoms"]),
        s_ages=list(s["ages"]),
        s_tags=list(s["tags"]),
        s_sort=str(s["sort"]),
    )


def _format_hit(
    i: int, fic_id: int, title: str, author_nick: str | None, fandom_name: str | None, likes: int
) -> str:
    author = f" — {author_nick}" if author_nick else ""
    fandom = f" · {fandom_name}" if fandom_name else ""
    return f"{i}. {title}{author}{fandom} · ❤️ {likes}"


@router.callback_query(SearchCD.filter(F.a == "filters_root"))
async def show_filters_root(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    await state.set_state(SearchFiltersFSM.selecting)
    kb = filters_root_kb(
        fandoms_selected=len(s["fandoms"]),
        ages_selected=len(s["ages"]),
        tags_selected=len(s["tags"]),
        sort=str(s["sort"]),
    )
    body = "🔎 *Поиск*\nВыбери фильтры и нажми «Показать»."
    try:
        await cb.message.edit_text(body, reply_markup=kb, parse_mode="Markdown")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        await cb.message.answer(body, reply_markup=kb, parse_mode="Markdown")
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "pick_fandom"))
@inject
async def pick_search_fandom(
    cb: CallbackQuery,
    callback_data: SearchCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    selected_ids: set[int] = {int(x) for x in s["fandoms"]}
    page = callback_data.pg
    fandoms, total = await reference.list_fandoms_paginated(
        limit=_SEARCH_FANDOMS_PER_PAGE,
        offset=page * _SEARCH_FANDOMS_PER_PAGE,
        active_only=True,
    )
    has_more = (page + 1) * _SEARCH_FANDOMS_PER_PAGE < total
    kb = search_fandom_picker_kb(
        fandoms=fandoms, selected_ids=selected_ids, page=page, has_more=has_more
    )
    try:
        await cb.message.edit_text("🎭 Выбери фандомы (мультиселект):", reply_markup=kb)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        await cb.message.answer("🎭 Выбери фандомы (мультиселект):", reply_markup=kb)
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "pick_age"))
@inject
async def pick_search_age(
    cb: CallbackQuery,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    items = await reference.list_age_ratings()
    kb = age_rating_picker_kb(items=items, selected_codes={str(x) for x in s["ages"]})
    try:
        await cb.message.edit_text("🔞 Выбери возраст (мультиселект):", reply_markup=kb)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        await cb.message.answer("🔞 Выбери возраст (мультиселект):", reply_markup=kb)
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "pick_tag"))
@inject
async def pick_search_tag(
    cb: CallbackQuery,
    state: FSMContext,
    suggest_reader: FromDishka[ISuggestReader],
) -> None:
    """Показать топ-N freeform-тегов (по usage_count)."""
    if cb.message is None:
        await cb.answer()
        return
    tag_names = await suggest_reader.by_prefix(
        kind="freeform", prefix="", limit=_POPULAR_TAGS_COUNT
    )
    s = await _get_search_state(state)
    kb = tag_picker_kb(tag_names=tag_names, selected={str(x) for x in s["tags"]})
    try:
        await cb.message.edit_text("🏷 Выбери теги (мультиселект):", reply_markup=kb)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        await cb.message.answer("🏷 Выбери теги (мультиселект):", reply_markup=kb)
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "pick_sort"))
async def pick_search_sort(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    kb = sort_picker_kb(str(s["sort"]))
    try:
        await cb.message.edit_text("⇅ Сортировка:", reply_markup=kb)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        await cb.message.answer("⇅ Сортировка:", reply_markup=kb)
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "toggle"))
@inject
async def toggle_filter(
    cb: CallbackQuery,
    callback_data: SearchCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
    suggest_reader: FromDishka[ISuggestReader],
) -> None:
    """Toggle одного элемента мультиселекта и перерисовать ТЕКУЩИЙ picker.

    Пользователь выходит в root только по кнопке «✅ Готово».
    """
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    kind = callback_data.k
    val = callback_data.v
    if kind == "fandom":
        lst = list(s["fandoms"])
        vi = int(val)
        if vi in lst:
            lst.remove(vi)
        else:
            lst.append(vi)
        s["fandoms"] = lst
    elif kind == "age":
        lst_s = list(s["ages"])
        if val in lst_s:
            lst_s.remove(val)
        else:
            lst_s.append(val)
        s["ages"] = lst_s
    elif kind == "tag":
        lst_s = list(s["tags"])
        if val in lst_s:
            lst_s.remove(val)
        else:
            lst_s.append(val)
        s["tags"] = lst_s
    await _save_search_state(state, s)
    await cb.answer()

    # Перерисовать текущий picker: edit только reply_markup, текст остаётся.
    kb = None
    if kind == "fandom":
        page = int(callback_data.pg)
        fandoms, total = await reference.list_fandoms_paginated(
            limit=_SEARCH_FANDOMS_PER_PAGE,
            offset=page * _SEARCH_FANDOMS_PER_PAGE,
            active_only=True,
        )
        has_more = (page + 1) * _SEARCH_FANDOMS_PER_PAGE < total
        kb = search_fandom_picker_kb(
            fandoms=fandoms,
            selected_ids={int(x) for x in s["fandoms"]},
            page=page,
            has_more=has_more,
        )
    elif kind == "age":
        items = await reference.list_age_ratings()
        kb = age_rating_picker_kb(items=items, selected_codes={str(x) for x in s["ages"]})
    elif kind == "tag":
        tag_names = await suggest_reader.by_prefix(
            kind="freeform", prefix="", limit=_POPULAR_TAGS_COUNT
        )
        kb = tag_picker_kb(tag_names=tag_names, selected={str(x) for x in s["tags"]})

    if kb is None:
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=kb)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — edit может фейлиться при одинаковом markup; молча игнорируем
        pass


@router.callback_query(SearchCD.filter(F.a == "set_sort"))
async def set_sort(cb: CallbackQuery, callback_data: SearchCD, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    s["sort"] = callback_data.v or _DEFAULT_SORT
    await _save_search_state(state, s)
    kb = filters_root_kb(
        fandoms_selected=len(s["fandoms"]),
        ages_selected=len(s["ages"]),
        tags_selected=len(s["tags"]),
        sort=str(s["sort"]),
    )
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            "🔎 *Поиск*\nВыбери фильтры и нажми «Показать».",
            reply_markup=kb,
            parse_mode="Markdown",
        )
    except Exception:  # noqa: BLE001
        pass
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "reset"))
async def reset_filters(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(s_fandoms=[], s_ages=[], s_tags=[], s_sort=_DEFAULT_SORT)
    await cb.answer("Сброшено")
    await show_filters_root(cb, state)  # type: ignore[arg-type]


@router.callback_query(SearchCD.filter(F.a.in_({"apply", "page"})))
@inject
async def apply_filters(
    cb: CallbackQuery,
    callback_data: SearchCD,
    state: FSMContext,
    search_uc: FromDishka[SearchUseCase],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    page = callback_data.pg if callback_data.a == "page" else 0
    cmd = SearchCommand(
        q="",
        fandoms=[int(x) for x in s["fandoms"]],
        age_ratings=[str(x) for x in s["ages"]],
        tags=[str(x) for x in s["tags"]],
        sort=str(s["sort"]),  # type: ignore[arg-type]
        limit=_PAGE_SIZE,
        offset=page * _PAGE_SIZE,
    )
    result = await search_uc(cmd)

    await state.set_state(SearchFiltersFSM.browsing)
    header = "🔎 *Поиск*"
    if result.degraded:
        header += "\n⚠️ Упрощённый режим — фильтры временно недоступны."

    if not result.hits:
        body = f"{header}\n\nНичего не найдено. Попробуй изменить фильтры."
    else:
        lines = [header, f"Найдено: {result.total}", ""]
        for idx, h in enumerate(result.hits, start=page * _PAGE_SIZE + 1):
            lines.append(
                _format_hit(
                    idx,
                    int(h.fic_id),
                    h.title,
                    h.author_nick,
                    h.fandom_name,
                    h.likes_count,
                )
            )
        body = "\n".join(lines)

    has_more = len(result.hits) == _PAGE_SIZE
    kb = results_kb(
        hits=[(int(h.fic_id), h.title) for h in result.hits],
        page=page,
        has_more=has_more,
        degraded=result.degraded,
    )
    try:
        await cb.message.edit_text(body, reply_markup=kb, parse_mode="Markdown")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        await cb.message.answer(body, reply_markup=kb, parse_mode="Markdown")
    await cb.answer()
