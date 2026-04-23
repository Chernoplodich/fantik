"""Роутер читалки: карточка фика, страницы, лайки, закладки, дочитано."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka, inject

from app.application.fanfics.ports import (
    IChapterRepository,
    IFanficRepository,
)
from app.application.users.ports import IUserRepository
from app.application.reading.mark_completed import (
    MarkCompletedCommand,
    MarkCompletedUseCase,
)
from app.application.reading.open_fanfic import (
    OpenFanficCommand,
    OpenFanficUseCase,
)
from app.application.reading.ports import (
    IChapterPagesRepository,
    IPageCache,
)
from app.application.reading.read_page import (
    ReadPageCommand,
    ReadPageUseCase,
)
from app.application.reading.save_progress import (
    SaveProgressCommand,
    SaveProgressUseCase,
)
from app.application.reading.toggle_bookmark import (
    ToggleBookmarkCommand,
    ToggleBookmarkUseCase,
)
from app.application.reading.toggle_like import (
    ToggleLikeCommand,
    ToggleLikeUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FanficId
from app.infrastructure.telegram.reader_renderer import (
    build_cover_caption,
    build_reader_message,
)
from app.presentation.bot.callback_data.reader import ReadNav
from app.presentation.bot.keyboards.reader import (
    cover_kb,
    reader_kb,
    toc_kb,
)

log = get_logger(__name__)
router = Router(name="reader")


# ---------- open: карточка фика ----------


@router.callback_query(ReadNav.filter(F.a == "open"))
@inject
async def open_fanfic(
    cb: CallbackQuery,
    callback_data: ReadNav,
    open_uc: FromDishka[OpenFanficUseCase],
    users: FromDishka[IUserRepository],
    bot: FromDishka[Bot],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await open_uc(OpenFanficCommand(user_id=cb.from_user.id, fic_id=callback_data.f))
    except DomainError as e:
        await cb.answer(str(e) or "Фик недоступен.", show_alert=True)
        return

    fic = result.fic
    author = await users.get(fic.author_id)
    caption, caption_entities = build_cover_caption(fic, author.author_nick if author else None)

    kb = cover_kb(
        fic_id=int(fic.id),
        has_progress=result.has_progress,
        progress_chapter_no=result.progress_chapter_number,
        progress_page_no=result.progress_page_no,
    )

    if fic.cover_file_id:
        try:
            await bot.send_photo(
                chat_id=cb.from_user.id,
                photo=fic.cover_file_id,
                caption=caption,
                caption_entities=caption_entities or None,  # type: ignore[arg-type]
                reply_markup=kb,
            )
        except TelegramBadRequest:
            await bot.send_message(
                chat_id=cb.from_user.id,
                text=caption,
                entities=caption_entities or None,  # type: ignore[arg-type]
                reply_markup=kb,
            )
    else:
        await bot.send_message(
            chat_id=cb.from_user.id,
            text=caption,
            entities=caption_entities or None,  # type: ignore[arg-type]
            reply_markup=kb,
        )
    await cb.answer()


# ---------- read: переход к странице (с удалением cover / edit_message_text) ----------


@router.callback_query(ReadNav.filter(F.a == "read"))
@inject
async def start_reading(
    cb: CallbackQuery,
    callback_data: ReadNav,
    read_uc: FromDishka[ReadPageUseCase],
    save_progress_uc: FromDishka[SaveProgressUseCase],
    fanfics: FromDishka[IFanficRepository],
    chapters_repo: FromDishka[IChapterRepository],
    page_cache: FromDishka[IPageCache],
    pages_repo: FromDishka[IChapterPagesRepository],
    bot: FromDishka[Bot],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return

    fic = await fanfics.get(FanficId(callback_data.f))
    if fic is None or fic.status != FicStatus.APPROVED:
        await cb.answer("Фик недоступен.", show_alert=True)
        return
    chapters = [
        c for c in await chapters_repo.list_by_fic(fic.id) if c.status == FicStatus.APPROVED
    ]
    if not chapters:
        await cb.answer("У фика пока нет опубликованных глав.", show_alert=True)
        return
    chapters.sort(key=lambda c: int(c.number))

    # Если callback_data.c/p заданы ≥ 1 — «Продолжить» с этой позиции; иначе
    # открываем первую главу со страницы 1.
    target_chapter_no = callback_data.c if callback_data.c >= 1 else int(chapters[0].number)
    target_page = callback_data.p if callback_data.p >= 1 else 1
    target_chapter = next(
        (c for c in chapters if int(c.number) == target_chapter_no), None
    )
    if target_chapter is None:
        target_chapter = chapters[0]
        target_page = 1

    try:
        result = await read_uc(
            ReadPageCommand(
                user_id=cb.from_user.id,
                fic_id=int(fic.id),
                chapter_id=int(target_chapter.id),
                page_no=target_page,
            )
        )
    except DomainError as e:
        # Страница вне диапазона (глава могла стать короче после правки) —
        # fallback на первую страницу этой же главы.
        if target_page != 1:
            try:
                result = await read_uc(
                    ReadPageCommand(
                        user_id=cb.from_user.id,
                        fic_id=int(fic.id),
                        chapter_id=int(target_chapter.id),
                        page_no=1,
                    )
                )
                target_page = 1
            except DomainError as e2:
                await cb.answer(str(e2) or "Не удалось открыть главу.", show_alert=True)
                return
        else:
            await cb.answer(str(e) or "Не удалось открыть главу.", show_alert=True)
            return

    # Удаляем cover-сообщение (фото нельзя edit_message_text).
    try:
        await cb.message.delete()  # type: ignore[union-attr]
    except TelegramBadRequest:
        pass

    text, entities = build_reader_message(
        fic=fic,
        chapter=target_chapter,
        page=result.page,
        total_pages=result.total_pages,
    )
    kb = reader_kb(
        fic_id=int(fic.id),
        chapter_no=int(target_chapter.number),
        page_no=int(result.page.page_no),
        total_pages=result.total_pages,
        total_chapters=result.total_chapters,
        is_bookmarked=result.is_bookmarked,
        is_liked=result.is_liked,
        is_last_page_in_chapter=result.is_last_page_in_chapter,
        is_last_page_of_fic=result.is_last_page_of_fic,
        already_completed=result.already_completed,
    )
    await bot.send_message(
        chat_id=cb.from_user.id,
        text=text,
        entities=entities or None,  # type: ignore[arg-type]
        reply_markup=kb,
    )

    await _save_progress_safe(
        save_progress_uc,
        user_id=cb.from_user.id,
        fic_id=int(fic.id),
        chapter_id=int(target_chapter.id),
        page_no=int(result.page.page_no),
    )
    _prefetch(
        page_cache, pages_repo, chapters_repo, int(target_chapter.id),
        int(result.page.page_no) + 1,
    )
    await cb.answer()


# ---------- prev / next / chapter: edit_message_text ----------


@router.callback_query(ReadNav.filter(F.a.in_({"prev", "next", "chapter"})))
@inject
async def navigate(
    cb: CallbackQuery,
    callback_data: ReadNav,
    read_uc: FromDishka[ReadPageUseCase],
    save_progress_uc: FromDishka[SaveProgressUseCase],
    fanfics: FromDishka[IFanficRepository],
    chapters_repo: FromDishka[IChapterRepository],
    page_cache: FromDishka[IPageCache],
    pages_repo: FromDishka[IChapterPagesRepository],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return

    fic_id = FanficId(callback_data.f)
    fic = await fanfics.get(fic_id)
    if fic is None or fic.status != FicStatus.APPROVED:
        await cb.answer("Фик недоступен.", show_alert=True)
        return

    chapter = await _resolve_chapter_by_number(chapters_repo, fic_id, callback_data.c)
    if chapter is None:
        await cb.answer("Глава не найдена.", show_alert=True)
        return

    try:
        result = await read_uc(
            ReadPageCommand(
                user_id=cb.from_user.id,
                fic_id=int(fic_id),
                chapter_id=int(chapter.id),
                page_no=callback_data.p or 1,
            )
        )
    except DomainError as e:
        await cb.answer(str(e) or "Страница не найдена.", show_alert=True)
        return

    text, entities = build_reader_message(
        fic=fic,
        chapter=chapter,
        page=result.page,
        total_pages=result.total_pages,
    )
    kb = reader_kb(
        fic_id=int(fic_id),
        chapter_no=int(chapter.number),
        page_no=int(result.page.page_no),
        total_pages=result.total_pages,
        total_chapters=result.total_chapters,
        is_bookmarked=result.is_bookmarked,
        is_liked=result.is_liked,
        is_last_page_in_chapter=result.is_last_page_in_chapter,
        is_last_page_of_fic=result.is_last_page_of_fic,
        already_completed=result.already_completed,
    )
    try:
        await cb.message.edit_text(  # type: ignore[union-attr]
            text=text,
            entities=entities or None,  # type: ignore[arg-type]
            reply_markup=kb,
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            # Дубль-клик — тихо.
            pass
        else:
            log.warning("reader_edit_failed", error=str(e))
            await cb.answer("Не удалось обновить сообщение.", show_alert=False)
            return

    await _save_progress_safe(
        save_progress_uc,
        user_id=cb.from_user.id,
        fic_id=int(fic_id),
        chapter_id=int(chapter.id),
        page_no=int(result.page.page_no),
    )
    _prefetch(
        page_cache,
        pages_repo,
        chapters_repo,
        int(chapter.id),
        int(result.page.page_no) + 1,
    )
    await cb.answer()


# ---------- toc ----------


@router.callback_query(ReadNav.filter(F.a == "toc"))
@inject
async def show_toc(
    cb: CallbackQuery,
    callback_data: ReadNav,
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    fic_id = FanficId(callback_data.f)
    chapters = [
        c for c in await chapters_repo.list_by_fic(fic_id) if c.status == FicStatus.APPROVED
    ]
    chapters.sort(key=lambda c: int(c.number))
    try:
        await cb.message.edit_reply_markup(  # type: ignore[union-attr]
            reply_markup=toc_kb(
                fic_id=callback_data.f,
                chapters=chapters,
                current_chapter_no=callback_data.c,
            )
        )
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------- bookmark / like / report / complete ----------


@router.callback_query(ReadNav.filter(F.a == "bookmark"))
@inject
async def toggle_bookmark(
    cb: CallbackQuery,
    callback_data: ReadNav,
    uc: FromDishka[ToggleBookmarkUseCase],
    read_uc: FromDishka[ReadPageUseCase],
    fanfics: FromDishka[IFanficRepository],
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await uc(ToggleBookmarkCommand(user_id=cb.from_user.id, fic_id=callback_data.f))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("Добавлено в закладки." if result.now_bookmarked else "Убрано из закладок.")
    await _refresh_keyboard(cb, callback_data, read_uc, fanfics, chapters_repo)


@router.callback_query(ReadNav.filter(F.a == "like"))
@inject
async def toggle_like(
    cb: CallbackQuery,
    callback_data: ReadNav,
    uc: FromDishka[ToggleLikeUseCase],
    read_uc: FromDishka[ReadPageUseCase],
    fanfics: FromDishka[IFanficRepository],
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await uc(ToggleLikeCommand(user_id=cb.from_user.id, fic_id=callback_data.f))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("❤️ Добавлен лайк." if result.now_liked else "Лайк убран.")
    await _refresh_keyboard(cb, callback_data, read_uc, fanfics, chapters_repo)


@router.callback_query(ReadNav.filter(F.a == "report"))
async def report_stub(cb: CallbackQuery) -> None:
    await cb.answer(
        "Жалобы появятся в следующих обновлениях.",
        show_alert=True,
    )


@router.callback_query(ReadNav.filter(F.a == "complete"))
@inject
async def mark_completed(
    cb: CallbackQuery,
    callback_data: ReadNav,
    uc: FromDishka[MarkCompletedUseCase],
    read_uc: FromDishka[ReadPageUseCase],
    fanfics: FromDishka[IFanficRepository],
    chapters_repo: FromDishka[IChapterRepository],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    chapter = await _resolve_chapter_by_number(
        chapters_repo, FanficId(callback_data.f), callback_data.c
    )
    if chapter is None:
        await cb.answer("Глава не найдена.", show_alert=True)
        return
    try:
        result = await uc(
            MarkCompletedCommand(
                user_id=cb.from_user.id,
                fic_id=callback_data.f,
                chapter_id=int(chapter.id),
            )
        )
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("✓ Дочитано!" if result.fic_completed else "Отмечено.")
    await _refresh_keyboard(cb, callback_data, read_uc, fanfics, chapters_repo)


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()


# ---------- helpers ----------


async def _resolve_chapter_by_number(
    chapters_repo: IChapterRepository,
    fic_id: FanficId,
    chapter_no: int,
) -> Any:
    """Вернуть approved-главу фика по номеру (None если нет)."""
    chapters = [
        c for c in await chapters_repo.list_by_fic(fic_id) if c.status == FicStatus.APPROVED
    ]
    for c in chapters:
        if int(c.number) == int(chapter_no):
            return c
    return None


async def _save_progress_safe(
    uc: SaveProgressUseCase,
    *,
    user_id: int,
    fic_id: int,
    chapter_id: int,
    page_no: int,
) -> None:
    try:
        await uc(
            SaveProgressCommand(
                user_id=user_id,
                fic_id=fic_id,
                chapter_id=chapter_id,
                page_no=page_no,
            )
        )
    except Exception as e:
        log.warning("save_progress_failed", error=str(e))


def _prefetch(
    page_cache: IPageCache,
    pages_repo: IChapterPagesRepository,
    chapters_repo: IChapterRepository,
    chapter_id: int,
    page_no: int,
) -> None:
    """No-op placeholder под будущий prefetch.

    В Stage 3 оставлен пустым: фоновая задача переживает dishka-scope и не может
    безопасно использовать AsyncSession. Нормальный путь: handler в next-клике
    строит/кэширует страницу через read_page. При hit ~10 ms, при miss — один
    проход `ChapterPaginator.paginate` (≤ 50 ms для 100 k units).

    TODO (Stage 7): прогрев N+1 через отдельный dishka-scope или TaskIQ с
    «light»-приоритетом.
    """
    del page_cache, pages_repo, chapters_repo, chapter_id, page_no


async def _refresh_keyboard(
    cb: CallbackQuery,
    nav: ReadNav,
    read_uc: ReadPageUseCase,
    fanfics: IFanficRepository,
    chapters_repo: IChapterRepository,
) -> None:
    """После toggle — перерисовываем клавиатуру (иконки ❤️/📑)."""
    if cb.message is None or cb.from_user is None:
        return
    fic_id = FanficId(nav.f)
    fic = await fanfics.get(fic_id)
    if fic is None:
        return
    chapter = await _resolve_chapter_by_number(chapters_repo, fic_id, nav.c)
    if chapter is None:
        return
    try:
        result = await read_uc(
            ReadPageCommand(
                user_id=cb.from_user.id,
                fic_id=int(fic_id),
                chapter_id=int(chapter.id),
                page_no=nav.p or 1,
            )
        )
    except DomainError:
        return
    kb = reader_kb(
        fic_id=int(fic_id),
        chapter_no=int(chapter.number),
        page_no=int(result.page.page_no),
        total_pages=result.total_pages,
        total_chapters=result.total_chapters,
        is_bookmarked=result.is_bookmarked,
        is_liked=result.is_liked,
        is_last_page_in_chapter=result.is_last_page_in_chapter,
        is_last_page_of_fic=result.is_last_page_of_fic,
        already_completed=result.already_completed,
    )
    try:
        await cb.message.edit_reply_markup(reply_markup=kb)  # type: ignore[union-attr]
    except TelegramBadRequest:
        pass
