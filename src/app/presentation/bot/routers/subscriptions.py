"""Роутер подписок: подписка/отписка с карточки фика."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from dishka.integrations.aiogram import FromDishka, inject

from app.application.reading.open_fanfic import (
    OpenFanficCommand,
    OpenFanficUseCase,
)
from app.application.subscriptions.subscribe import (
    SubscribeCommand,
    SubscribeUseCase,
)
from app.application.subscriptions.unsubscribe import (
    UnsubscribeCommand,
    UnsubscribeUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.presentation.bot.callback_data.social import SubNav
from app.presentation.bot.keyboards.reader import cover_kb

log = get_logger(__name__)
router = Router(name="subscriptions")


@router.callback_query(SubNav.filter(F.a == "sub"))
@inject
async def subscribe(
    cb: CallbackQuery,
    callback_data: SubNav,
    uc: FromDishka[SubscribeUseCase],
    open_uc: FromDishka[OpenFanficUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await uc(SubscribeCommand(subscriber_id=cb.from_user.id, fic_id=callback_data.f))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("🔔 Подписка оформлена" if result.created else "🔔 Уже подписан(а)")
    await _refresh_cover(cb, fic_id=callback_data.f, is_subscribed=True, open_uc=open_uc)


@router.callback_query(SubNav.filter(F.a == "unsub"))
@inject
async def unsubscribe(
    cb: CallbackQuery,
    callback_data: SubNav,
    uc: FromDishka[UnsubscribeUseCase],
    open_uc: FromDishka[OpenFanficUseCase],
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        result = await uc(UnsubscribeCommand(subscriber_id=cb.from_user.id, fic_id=callback_data.f))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("🔕 Подписка снята" if result.removed else "🔕 Подписки не было")
    await _refresh_cover(cb, fic_id=callback_data.f, is_subscribed=False, open_uc=open_uc)


async def _refresh_cover(
    cb: CallbackQuery,
    *,
    fic_id: int,
    is_subscribed: bool,
    open_uc: OpenFanficUseCase,
) -> None:
    """Переотрисовать клавиатуру на карточке после sub/unsub."""
    if cb.from_user is None or cb.message is None:
        return
    try:
        result = await open_uc(OpenFanficCommand(user_id=cb.from_user.id, fic_id=fic_id))
    except DomainError:
        return

    fic = result.fic
    show_subscribe = int(fic.author_id) != int(cb.from_user.id)

    kb = cover_kb(
        fic_id=int(fic.id),
        has_progress=result.has_progress,
        progress_chapter_no=result.progress_chapter_number,
        progress_page_no=result.progress_page_no,
        is_subscribed=is_subscribed,
        show_subscribe=show_subscribe,
    )
    try:
        await cb.message.edit_reply_markup(reply_markup=kb)  # type: ignore[union-attr]
    except TelegramBadRequest:
        log.debug("sub_refresh_cover_failed", fic_id=fic_id)
