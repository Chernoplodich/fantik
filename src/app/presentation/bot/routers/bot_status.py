"""Роутер статуса бота у юзера: my_chat_member события.

Telegram шлёт `my_chat_member` update при изменении статуса бота в чате:
- юзер заблокировал бота (new.status='kicked')
- юзер разблокировал (new.status='member' после 'kicked')

Отмечаем `users.blocked_bot_at`, чтобы:
- исключать заблокировавших из сегментов рассылки,
- считать их отдельно в статистике.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import ChatMemberUpdated
from dishka.integrations.aiogram import FromDishka, inject

from app.application.shared.ports import UnitOfWork
from app.application.users.ports import IUserRepository
from app.core.logging import get_logger
from app.domain.shared.types import UserId

log = get_logger(__name__)
router = Router(name="bot_status")


@router.my_chat_member(F.chat.type == "private")
@inject
async def on_my_chat_member(
    event: ChatMemberUpdated,
    users: FromDishka[IUserRepository],
    uow: FromDishka[UnitOfWork],
) -> None:
    """Обработать изменение статуса бота в приватном чате с юзером."""
    new_status = event.new_chat_member.status
    user_id = UserId(int(event.chat.id))

    if new_status == "kicked":
        async with uow:
            await users.mark_bot_blocked(user_id)
            await uow.commit()
        log.info("bot_blocked_by_user", user_id=int(user_id))
    elif new_status in {"member", "administrator"}:
        async with uow:
            await users.clear_bot_blocked(user_id)
            await uow.commit()
        log.info("bot_unblocked_by_user", user_id=int(user_id))
