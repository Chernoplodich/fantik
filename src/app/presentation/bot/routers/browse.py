"""Каталог: /catalog + ленты «Новое» / «Топ» / «По фэндому» + поиск с фильтрами."""

from __future__ import annotations

from aiogram import Bot, F, Router
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
from app.presentation.bot.callback_data.browse import BrowseCD, QuickQCD
from app.presentation.bot.callback_data.search import SearchCD
from app.presentation.bot.fandom_categories import (
    CATEGORIES,
    category_long_label,
    get_category,
)
from app.presentation.bot.fsm.states.browse import BrowseStates
from app.presentation.bot.fsm.states.search import SearchFiltersFSM
from app.presentation.bot.keyboards.browse import browse_root_kb
from app.presentation.bot.keyboards.fandom_picker import (
    FANDOMS_PER_PAGE as PICKER_PAGE_SIZE,
)
from app.presentation.bot.keyboards.fandom_picker import (
    build_categories_kb,
    build_fandoms_in_category_kb,
    build_search_results_kb,
)
from app.presentation.bot.keyboards.reader import feed_kb
from app.presentation.bot.keyboards.search_filters import (
    age_rating_picker_kb,
    filters_root_kb,
    query_input_kb_advanced,
    query_input_kb_quick,
    results_kb,
    sort_picker_kb,
    tag_picker_kb,
)
from app.presentation.bot.texts.ru import t
from app.presentation.bot.ui_helpers import render

log = get_logger(__name__)
router = Router(name="browse")

_PAGE_SIZE = 10
_POPULAR_TAGS_COUNT = 24
_DEFAULT_SORT: SortMode = "relevance"
_FANDOM_SEARCH_LIMIT = 20
_MIN_QUERY_LEN = 2


# ---------- root ----------


_BOT_USERNAME_CACHE: str | None = None


async def _bot_username(bot: "Bot | None") -> str | None:
    """Закэшировать @username бота на процесс. Используется для inline-подсказки.

    Если по какой-то причине getMe не отвечает (rate-limit, токен) — молча None,
    UI просто не покажет подсказку.
    """
    global _BOT_USERNAME_CACHE
    if _BOT_USERNAME_CACHE is not None:
        return _BOT_USERNAME_CACHE
    if bot is None:
        return None
    try:
        me = await bot.get_me()
    except Exception:  # noqa: BLE001
        return None
    if me.username:
        _BOT_USERNAME_CACHE = str(me.username)
    return _BOT_USERNAME_CACHE


def _catalog_root_text(bot_username: str | None) -> str:
    body = "📚 <b>Каталог работ</b>"
    if bot_username:
        body += (
            "\n\n💡 <i>В любом чате набери</i> "
            f"<code>@{bot_username} слово</code> "
            "<i>— быстрый поиск работ без открытия бота.</i>"
        )
    return body


@router.message(Command("catalog"))
@inject
async def cmd_catalog(
    message: Message,
    state: FSMContext,
    bot: FromDishka[Bot],
) -> None:
    await state.update_data(_qk_active=False, qk_q="", qk_fandoms=[])
    body = _catalog_root_text(await _bot_username(bot))
    await message.answer(body, reply_markup=browse_root_kb(), parse_mode="HTML")


@router.callback_query(F.data == "menu:browse")
@router.callback_query(BrowseCD.filter(F.a == "root"))
@inject
async def show_root(
    cb: CallbackQuery,
    state: FSMContext,
    bot: FromDishka[Bot],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    # Возвращение в каталог = выход из quick-сессии: чистим quick-namespace,
    # чтобы он не «всплыл» при следующем нажатии «✏️ Найти по слову».
    await state.update_data(_qk_active=False, qk_q="", qk_fandoms=[])
    body = _catalog_root_text(await _bot_username(bot))
    await render(cb, body, reply_markup=browse_root_kb(), parse_mode="HTML")
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
        from app.presentation.bot.display import display_author_nick

        lines = [header, ""]
        for idx, it in enumerate(items, start=page * _PAGE_SIZE + 1):
            nick = display_author_nick(it.author_nick)
            author = f" — {nick}" if nick else ""
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
    await render(cb, body, reply_markup=kb)


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


# ---------- by_fandom: pick → feed (каталог) ----------


_BY_FANDOM_INTRO = (
    "🎭 <b>Выбери фандом</b>\n\n"
    "Где искать?\nВыбери категорию или нажми «🔍 Найти по названию»."
)


async def _show_browse_categories(cb: CallbackQuery, state: FSMContext) -> None:
    """Показать корень пикера фандомов в browse-режиме (категории)."""
    if cb.message is None:
        await cb.answer()
        return
    # На корне категорий FSM не нужен, но сбросим — мог остаться от предыдущего поиска.
    if await state.get_state() == BrowseStates.entering_fandom_search.state:
        await state.clear()
    kb = build_categories_kb(flow="browse", show_propose=False)
    await render(cb, _BY_FANDOM_INTRO, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(BrowseCD.filter(F.a == "by_fandom"))
@router.callback_query(BrowseCD.filter(F.a == "fcats"))
async def browse_categories(cb: CallbackQuery, state: FSMContext) -> None:
    """Корень «🎭 По фэндому» — список категорий."""
    await _show_browse_categories(cb, state)


@router.callback_query(BrowseCD.filter(F.a == "fcat"))
@inject
async def browse_fandoms_in_category(
    cb: CallbackQuery,
    callback_data: BrowseCD,
    reference: FromDishka[IReferenceReader],
) -> None:
    """Показать фандомы внутри выбранной категории (single-select для browse)."""
    if cb.message is None:
        await cb.answer()
        return
    cat_code = (callback_data.v or "other").lower()
    page = max(0, callback_data.pg)
    fandoms, total = await reference.list_fandoms_by_category(
        category=cat_code,
        limit=PICKER_PAGE_SIZE,
        offset=page * PICKER_PAGE_SIZE,
        active_only=True,
    )
    has_more = (page + 1) * PICKER_PAGE_SIZE < total
    kb = build_fandoms_in_category_kb(
        flow="browse",
        cat=cat_code,
        fandoms=fandoms,
        page=page,
        has_more=has_more,
    )
    body = (
        f"<b>{category_long_label(cat_code)}</b>\n\n"
        "Выбери фандом — покажу работы из него."
    )
    if not fandoms:
        body = (
            f"<b>{category_long_label(cat_code)}</b>\n\n"
            "Пока пусто. Попробуй другую категорию или нажми «🔍 Найти по названию»."
        )
    await render(cb, body, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(BrowseCD.filter(F.a == "fsearch"))
async def browse_enter_fandom_search(cb: CallbackQuery, state: FSMContext) -> None:
    """Войти в FSM ввода подстроки имени фандома (browse-flow)."""
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(BrowseStates.entering_fandom_search)
    body = (
        "🔍 <b>Найти фандом</b>\n\n"
        "Напиши часть названия (минимум 2 символа). Можно по-русски или по-английски."
    )
    # Под prompt'ом — кнопка возврата к категориям, чтобы юзер не застрял
    # в ожидании ввода без явного выхода.
    from app.presentation.bot.callback_data.browse import BrowseCD as _BCD
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⟵ К категориям", callback_data=_BCD(a="fcats").pack())],
            [InlineKeyboardButton(text="⟵ Каталог", callback_data=_BCD(a="root").pack())],
        ]
    )
    await render(cb, body, reply_markup=cancel_kb, parse_mode="HTML")
    await cb.answer()


@router.message(BrowseStates.entering_fandom_search, F.text)
@inject
async def browse_on_fandom_search_text(
    message: Message,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await state.clear()
        return
    if len(raw) < _MIN_QUERY_LEN:
        await message.answer(t("search_q_too_short"))
        return
    try:
        fandoms = await reference.search_fandoms(
            query=raw, limit=_FANDOM_SEARCH_LIMIT, active_only=True
        )
    except Exception:  # noqa: BLE001
        log.exception("browse_fandom_search_failed", q=raw)
        await message.answer(
            "Не получилось выполнить поиск. Попробуй ещё раз или вернись к категориям."
        )
        return
    await state.clear()
    if not fandoms:
        kb = build_categories_kb(flow="browse", show_propose=False)
        await message.answer(
            f"По запросу «{raw}» ничего не нашлось. Попробуй другое слово или выбери категорию.",
            reply_markup=kb,
            parse_mode=None,
        )
        return
    kb = build_search_results_kb(flow="browse", fandoms=fandoms)
    await message.answer(f"По запросу «{raw}»:", reply_markup=kb)


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
        "q": str(data.get("s_q") or ""),
        "fandoms": list(data.get("s_fandoms") or []),
        "ages": list(data.get("s_ages") or []),
        "tags": list(data.get("s_tags") or []),
        "sort": str(data.get("s_sort") or _DEFAULT_SORT),
    }


async def _save_search_state(state: FSMContext, s: dict[str, object]) -> None:
    await state.update_data(
        s_q=str(s.get("q") or ""),
        s_fandoms=list(s["fandoms"]),
        s_ages=list(s["ages"]),
        s_tags=list(s["tags"]),
        s_sort=str(s["sort"]),
    )


def _format_hit(
    i: int, fic_id: int, title: str, author_nick: str | None, fandom_name: str | None, likes: int
) -> str:
    from app.presentation.bot.display import display_author_nick

    nick = display_author_nick(author_nick)
    author = f" — {nick}" if nick else ""
    fandom = f" · {fandom_name}" if fandom_name else ""
    return f"{i}. {title}{author}{fandom} · ❤️ {likes}"


async def _filter_labels(
    s: dict[str, object], reference: IReferenceReader
) -> tuple[str, str, str]:
    """Сформировать «человеческие» лейблы кнопок фильтра по текущему state.

    Если фильтр пустой — показываем «Любой …»; если выбран один — само значение
    (имя фандома, код рейтинга, тег); если несколько — «Выбрано: N».
    """
    # ---- fandom
    fandom_ids = [int(x) for x in s["fandoms"]]  # type: ignore[union-attr]
    if not fandom_ids:
        fandom_label = "🎭 Любой фандом"
    elif len(fandom_ids) == 1:
        ref = await reference.get_fandom(FandomId(fandom_ids[0]))
        if ref is not None:
            short = ref.name if len(ref.name) <= 22 else (ref.name[:21] + "…")
            fandom_label = f"🎭 {short}"
        else:
            fandom_label = "🎭 Выбрано: 1"
    else:
        fandom_label = f"🎭 Выбрано: {len(fandom_ids)}"

    # ---- age
    ages = [str(x) for x in s["ages"]]  # type: ignore[union-attr]
    if not ages:
        age_label = "🔞 Любой возраст"
    elif len(ages) == 1:
        age_label = f"🔞 {ages[0]}"
    else:
        age_label = f"🔞 Выбрано: {len(ages)}"

    # ---- tags (имена уже в state, ничего догружать не нужно)
    tags = [str(x) for x in s["tags"]]  # type: ignore[union-attr]
    if not tags:
        tag_label = "🏷 Без тегов"
    elif len(tags) == 1:
        short_tag = tags[0] if len(tags[0]) <= 18 else (tags[0][:17] + "…")
        tag_label = f"🏷 {short_tag}"
    else:
        tag_label = f"🏷 Выбрано: {len(tags)}"

    return fandom_label, age_label, tag_label


async def _root_kb_async(s: dict[str, object], reference: IReferenceReader) -> object:
    fandom_label, age_label, tag_label = await _filter_labels(s, reference)
    return filters_root_kb(
        fandom_label=fandom_label,
        age_label=age_label,
        tag_label=tag_label,
        sort=str(s["sort"]),
        query=str(s.get("q") or "") or None,
    )


_FILTERS_ROOT_TEXT = (
    "🔧 <b>Расширенный поиск</b>\n\n"
    "Комбинируй фильтры и нажми «🔎 Показать»."
)


@router.callback_query(SearchCD.filter(F.a == "filters_root"))
@inject
async def show_filters_root(
    cb: CallbackQuery,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    # Юзер явно открыл расширенный поиск. Чистим quick-namespace, чтобы
    # quick-данные из предыдущей сессии не сбивали с толку (например, чтобы
    # после quick «наруто» расширенный поиск не запомнил «наруто» в s_q).
    await state.update_data(_qk_active=False, qk_q="", qk_fandoms=[])
    await state.set_state(SearchFiltersFSM.selecting)
    kb = await _root_kb_async(s, reference)
    await render(cb, _FILTERS_ROOT_TEXT, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


# ---------- запрос (q) ----------


@router.callback_query(SearchCD.filter(F.a == "enter_q"))
async def enter_query(cb: CallbackQuery, state: FSMContext) -> None:
    """Вход в ввод свободного q из расширенного поиска.

    После сохранения q юзер возвращается в `filters_root` (а не сразу
    к результатам), чтобы он мог поправить остальные фильтры.
    """
    if cb.message is None:
        await cb.answer()
        return
    # Сбрасываем quick-namespace: переход «quick → advanced» не должен
    # уносить с собой quick-данные.
    await state.update_data(_qk_active=False, qk_q="", qk_fandoms=[])
    await state.set_state(SearchFiltersFSM.entering_query)
    await render(
        cb,
        t("search_q_prompt"),
        reply_markup=query_input_kb_advanced(),
        parse_mode="HTML",
    )
    await cb.answer()


async def _start_quick_query(
    cb: CallbackQuery,
    state: FSMContext,
    *,
    fandom_id: int = 0,
    fandom_name: str | None = None,
) -> None:
    """Универсальный вход в quick-поиск: чистый или с preset-фильтром по фандому.

    Quick-search полностью изолирован от расширенного поиска: использует
    собственный namespace в FSM-data (`_qk_active`, `qk_q`, `qk_fandoms`).
    Расширенные фильтры (`s_q`, `s_fandoms`, …) при этом НЕ трогаются —
    в следующий заход в «🔧 Расширенный поиск» юзер найдёт всё, что было.
    """
    if cb.message is None:
        await cb.answer()
        return
    await state.update_data(
        _qk_active=True,
        qk_q="",
        qk_fandoms=[int(fandom_id)] if fandom_id else [],
    )
    await state.set_state(SearchFiltersFSM.entering_query)
    if fandom_id and fandom_name:
        body = (
            f"✏️ <b>Поиск в фандоме «{fandom_name}»</b>\n\n"
            "Напиши слово из названия / описания / автора — "
            "найду только работы этого фандома.\n\nМинимум 2 символа."
        )
    elif fandom_id:
        body = (
            "✏️ <b>Поиск в выбранном фандоме</b>\n\n"
            "Напиши слово — найду только работы этого фандома.\n\nМинимум 2 символа."
        )
    else:
        body = (
            "✏️ <b>Поиск по слову</b>\n\n"
            "Найду <b>работы</b>, в названии / описании / у автора которых "
            "встречается твоё слово.\n\n"
            "Если хочешь все работы по фандому — лучше выбрать "
            "<b>🎭 По фэндому</b> в каталоге.\n\n"
            "Минимум 2 символа."
        )
    await render(cb, body, reply_markup=query_input_kb_quick(), parse_mode="HTML")
    await cb.answer()


@router.callback_query(QuickQCD.filter(F.a == "start"))
async def quick_query_start(cb: CallbackQuery, state: FSMContext) -> None:
    """Быстрый поиск из корня каталога — без preset-фандома."""
    await _start_quick_query(cb, state)


@router.callback_query(QuickQCD.filter(F.a == "in_fandom"))
@inject
async def quick_query_in_fandom(
    cb: CallbackQuery,
    callback_data: QuickQCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    """Быстрый поиск из ленты фандома: preset-фильтр `s_fandoms=[fd]`."""
    fid = int(callback_data.fd)
    fandom_name: str | None = None
    if fid:
        ref = await reference.get_fandom(FandomId(fid))
        fandom_name = ref.name if ref else None
    await _start_quick_query(cb, state, fandom_id=fid, fandom_name=fandom_name)


@router.callback_query(SearchCD.filter(F.a == "clear_q"))
async def clear_query(cb: CallbackQuery, state: FSMContext) -> None:
    s = await _get_search_state(state)
    s["q"] = ""
    await _save_search_state(state, s)
    await cb.answer(t("search_q_cleared"))
    await show_filters_root(cb, state)


@router.message(SearchFiltersFSM.entering_query, F.text)
@inject
async def on_query_text(
    message: Message,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
    search_uc: FromDishka[SearchUseCase],
) -> None:
    raw = (message.text or "").strip()
    # /start, /catalog и прочие команды не должны интерпретироваться как
    # значение запроса — пропускаем, чтобы команда могла отработать у
    # своего handler'а (cmd_start уже сделает state.clear()).
    if raw.startswith("/"):
        await state.clear()
        return
    if len(raw) < _MIN_QUERY_LEN:
        await message.answer(t("search_q_too_short"))
        return

    data = await state.get_data()
    quick_mode = bool(data.get("_qk_active"))
    q = raw[:200]  # защитный лимит

    if quick_mode:
        # Быстрый сценарий: сохраняем в quick-namespace (НЕ затрагивая `s_*`),
        # сразу показываем результаты. `_qk_active` остаётся True, чтобы
        # пагинация (`SearchCD a="page"`) тоже шла по quick-веткe.
        await state.update_data(qk_q=q)
        await _show_search_results(
            sender=message,
            state=state,
            search_uc=search_uc,
            page=0,
            reference=reference,
            quick=True,
        )
        return

    # Расширенный поиск: запоминаем в `s_q`, возвращаем в корень фильтров
    # с подтверждением. Юзер потом сам нажмёт «🔎 Показать».
    s = await _get_search_state(state)
    s["q"] = q
    await _save_search_state(state, s)
    await state.set_state(SearchFiltersFSM.selecting)
    kb = await _root_kb_async(s, reference)
    await message.answer(t("search_q_saved", q=q), reply_markup=kb)


# ---------- фандомы (двухступенчатый пикер) ----------


@router.callback_query(SearchCD.filter(F.a == "pick_fandom"))
async def pick_search_fandom(
    cb: CallbackQuery,
    state: FSMContext,
) -> None:
    """Открыть корень пикера фандомов: список категорий."""
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    await state.set_state(SearchFiltersFSM.selecting)
    kb = build_categories_kb(
        flow="search",
        selected_count=len(s["fandoms"]),  # type: ignore[arg-type]
        show_propose=False,
    )
    text = t("search_fandoms_help")
    await render(cb, text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "cat"))
@inject
async def pick_search_category(
    cb: CallbackQuery,
    callback_data: SearchCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    """Выбрана категория → показать список фандомов внутри неё."""
    if cb.message is None:
        await cb.answer()
        return
    cat_code = (callback_data.v or "other").lower()
    page = max(0, callback_data.pg)
    s = await _get_search_state(state)
    selected_ids: set[int] = {int(x) for x in s["fandoms"]}
    fandoms, total = await reference.list_fandoms_by_category(
        category=cat_code,
        limit=PICKER_PAGE_SIZE,
        offset=page * PICKER_PAGE_SIZE,
        active_only=True,
    )
    has_more = (page + 1) * PICKER_PAGE_SIZE < total
    kb = build_fandoms_in_category_kb(
        flow="search",
        cat=cat_code,
        fandoms=fandoms,
        page=page,
        has_more=has_more,
        selected_ids=selected_ids,
    )
    body = (
        f"<b>{category_long_label(cat_code)}</b>\n\n"
        "Можно отметить несколько — найдём работы из любой выбранной вселенной."
    )
    if not fandoms:
        body = (
            f"<b>{category_long_label(cat_code)}</b>\n\n"
            "Пока пусто. Попробуй другую категорию или нажми «🔍 Найти по названию»."
        )
    await render(cb, body, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "fsearch"))
async def enter_fandom_search(cb: CallbackQuery, state: FSMContext) -> None:
    """Перейти в FSM ввода подстроки имени фандома (для search-flow)."""
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(SearchFiltersFSM.entering_fandom_search)
    body = (
        "🔍 <b>Найти фандом</b>\n\n"
        "Напиши часть названия (минимум 2 символа). Можно по-русски или по-английски."
    )
    # Cancel-кнопки чтобы юзер мог выйти без ввода.
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⟵ К категориям",
                    callback_data=SearchCD(a="pick_fandom").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⟵ К фильтрам",
                    callback_data=SearchCD(a="filters_root").pack(),
                )
            ],
        ]
    )
    await render(cb, body, reply_markup=cancel_kb, parse_mode="HTML")
    await cb.answer()


@router.message(SearchFiltersFSM.entering_fandom_search, F.text)
@inject
async def on_fandom_search_text(
    message: Message,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    raw = (message.text or "").strip()
    # Команды (/start, /help, /catalog, …) — пропускаем, чтобы пользователь
    # мог в любой момент выйти из FSM. /start обработается cmd_start первым,
    # т.к. start_router зарегистрирован раньше browse_router; этот guard —
    # дополнительная страховка от непредвиденных сценариев.
    if raw.startswith("/"):
        await state.clear()
        return
    if len(raw) < _MIN_QUERY_LEN:
        await message.answer(t("search_q_too_short"))
        return
    try:
        fandoms = await reference.search_fandoms(
            query=raw, limit=_FANDOM_SEARCH_LIMIT, active_only=True
        )
    except Exception:  # noqa: BLE001 — SQL/connection guard
        log.exception("fandom_search_failed", q=raw)
        await message.answer(
            "Не получилось выполнить поиск. Попробуй ещё раз или вернись к категориям."
        )
        return
    s = await _get_search_state(state)
    selected_ids: set[int] = {int(x) for x in s["fandoms"]}
    if not fandoms:
        body = (
            f"По запросу «{raw}» ничего не нашлось. Попробуй другое слово или вернись к категориям."
        )
    else:
        body = f"По запросу «{raw}»:"
    kb = build_search_results_kb(flow="search", fandoms=fandoms, selected_ids=selected_ids)
    await state.set_state(SearchFiltersFSM.selecting)
    await message.answer(body, reply_markup=kb)


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
    body = t("search_age_help")
    await render(cb, body, reply_markup=kb, parse_mode="HTML")
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
    body = t("search_tags_help")
    await render(cb, body, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "pick_sort"))
async def pick_search_sort(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    kb = sort_picker_kb(str(s["sort"]))
    await render(cb, "⇅ Сортировка:", reply_markup=kb)
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
        # Для fandom мы остаёмся либо на странице категории (если pg в callback >= 0
        # и v=str(int)). К сожалению, callback_data toggle не знает категорию, поэтому
        # просто обновим клавиатуру под этой же страницей. Ищем категорию выбранного фандома.
        page = int(callback_data.pg)
        # Постараемся определить категорию по выбранному фандому: если он в s["fandoms"]
        # после toggle, читаем у него category. Но проще: грузим фандом по id.
        ref = await reference.get_fandom(FandomId(int(val)))
        cat_code = get_category(ref.category if ref else "other").code
        fandoms_in_cat, total_in_cat = await reference.list_fandoms_by_category(
            category=cat_code,
            limit=PICKER_PAGE_SIZE,
            offset=page * PICKER_PAGE_SIZE,
            active_only=True,
        )
        # Проверка: есть ли тот же fandom_id в списке этой страницы — иначе
        # пользователь пришёл с экрана search (без явной категории), и мы перерисовывать
        # категорию не должны. Перерисуем результаты search_fandoms по последнему
        # известному запросу — но мы его не храним. В таком случае оставим как есть и
        # просто покажем категорию.
        has_more = (page + 1) * PICKER_PAGE_SIZE < total_in_cat
        kb = build_fandoms_in_category_kb(
            flow="search",
            cat=cat_code,
            fandoms=fandoms_in_cat,
            page=page,
            has_more=has_more,
            selected_ids={int(x) for x in s["fandoms"]},
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
@inject
async def set_sort(
    cb: CallbackQuery,
    callback_data: SearchCD,
    state: FSMContext,
    reference: FromDishka[IReferenceReader],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    s = await _get_search_state(state)
    s["sort"] = callback_data.v or _DEFAULT_SORT
    await _save_search_state(state, s)
    kb = await _root_kb_async(s, reference)
    await render(cb, _FILTERS_ROOT_TEXT, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@router.callback_query(SearchCD.filter(F.a == "reset"))
async def reset_filters(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        s_q="",
        s_fandoms=[],
        s_ages=[],
        s_tags=[],
        s_sort=_DEFAULT_SORT,
    )
    await cb.answer("Сброшено")
    await show_filters_root(cb, state)


async def _show_search_results(
    *,
    sender: CallbackQuery | Message,
    state: FSMContext,
    search_uc: SearchUseCase,
    page: int,
    reference: IReferenceReader,
    quick: bool,
) -> None:
    """Запустить SearchUseCase и показать результаты.

    `quick=True` — данные из quick-namespace (`qk_q`, `qk_fandoms`),
    кнопка возврата ведёт в каталог, заголовок учитывает preset-фандом.
    `quick=False` — обычные расширенные фильтры (`s_q`, `s_fandoms`, …),
    кнопка возврата ведёт в расширенный поиск.
    """
    data = await state.get_data()
    if quick:
        q_text = str(data.get("qk_q") or "")
        fandoms_raw = list(data.get("qk_fandoms") or [])
        ages_raw: list[object] = []
        tags_raw: list[object] = []
        sort = _DEFAULT_SORT
        back_target = "catalog"
    else:
        q_text = str(data.get("s_q") or "")
        fandoms_raw = list(data.get("s_fandoms") or [])
        ages_raw = list(data.get("s_ages") or [])
        tags_raw = list(data.get("s_tags") or [])
        sort = str(data.get("s_sort") or _DEFAULT_SORT)
        back_target = "filters"

    fandoms = [int(x) for x in fandoms_raw]

    cmd = SearchCommand(
        q=q_text,
        fandoms=fandoms,
        age_ratings=[str(x) for x in ages_raw],
        tags=[str(x) for x in tags_raw],
        sort=sort,  # type: ignore[arg-type]
        limit=_PAGE_SIZE,
        offset=page * _PAGE_SIZE,
    )
    result = await search_uc(cmd)

    await state.set_state(SearchFiltersFSM.browsing)

    # Заголовок зависит от контекста: один фандом — пишем «Поиск в фандоме «X»»,
    # quick без фандома — «Поиск по слову», расширенный — «Поиск».
    if len(fandoms) == 1:
        ref = await reference.get_fandom(FandomId(fandoms[0]))
        header = (
            f"🔎 *Поиск в фандоме «{ref.name}»*"
            if ref is not None
            else "🔎 *Поиск в выбранном фандоме*"
        )
    elif quick:
        header = "🔎 *Поиск по слову*"
    else:
        header = "🔎 *Поиск*"
    if result.degraded:
        header += "\n⚠️ Упрощённый режим — фильтры временно недоступны."

    suggested: list[tuple[int, str]] = []
    if not result.hits and len(q_text) >= _MIN_QUERY_LEN and not fandoms:
        # При quick-search в фандоме (preset) подсказку «Открой фандом» не
        # показываем — юзер уже в нём; ему нужно другое слово, не фандом.
        try:
            matched = await reference.search_fandoms(query=q_text, limit=3, active_only=True)
            suggested = [(int(m.id), str(m.name)) for m in matched]
        except Exception:  # noqa: BLE001
            log.exception("fandom_suggest_failed", q=q_text)

    if not result.hits:
        body = f"{header}\n\nНичего не найдено."
        if suggested:
            body += (
                "\n\n💡 Похоже, ты ищешь весь фандом. "
                "Открой ленту по ссылке ниже:"
            )
        else:
            body += " Попробуй другое слово."
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
        suggested_fandoms=suggested,
        back_target=back_target,
    )

    # render() сам решает edit_text vs delete+send (для media-сообщений) и
    # игнорирует «message is not modified». Для message-вэвьюхи (quick-search
    # из ввода) вызывает event.answer.
    await render(sender, body, reply_markup=kb, parse_mode="Markdown")
    if isinstance(sender, CallbackQuery):
        await sender.answer()


@router.callback_query(SearchCD.filter(F.a.in_({"apply", "page"})))
@inject
async def apply_filters(
    cb: CallbackQuery,
    callback_data: SearchCD,
    state: FSMContext,
    search_uc: FromDishka[SearchUseCase],
    reference: FromDishka[IReferenceReader],
) -> None:
    """Пагинация и кнопка «🔎 Показать» — учитывают quick/advanced контекст
    через флаг `_qk_active` в FSM-data."""
    if cb.message is None:
        await cb.answer()
        return
    data = await state.get_data()
    is_quick = bool(data.get("_qk_active"))
    page = callback_data.pg if callback_data.a == "page" else 0
    await _show_search_results(
        sender=cb,
        state=state,
        search_uc=search_uc,
        page=page,
        reference=reference,
        quick=is_quick,
    )


# Удерживаем CATEGORIES от случайного удаления линтером (валидация по списку
# в логах при старте может пригодиться). Линтер всё равно не уберёт — он импортирован.
_ = CATEGORIES
