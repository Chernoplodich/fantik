"""FandomProposalNotifier: личные сообщения автору заявки на фандом.

Используется синхронно из админ-flow (после commit transaction).
TelegramAPIError не пробрасывается — логируем и игнорируем.
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.application.reference.ports import IFandomProposalNotifier
from app.domain.shared.types import FandomId, UserId

log = logging.getLogger(__name__)


class FandomProposalNotifier(IFandomProposalNotifier):
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify_submitted(self, *, requested_by: UserId, name: str) -> None:
        text = (
            "📨 <b>Заявка на новый фандом принята</b>\n\n"
            f"«{escape(name)}» отправлен на проверку. "
            "Когда модератор примет решение — пришлём уведомление."
        )
        await self._send(int(requested_by), text)

    async def notify_approved(
        self,
        *,
        requested_by: UserId,
        name: str,
        fandom_id: FandomId,
    ) -> None:
        text = (
            "✅ <b>Фандом одобрен</b>\n\n"
            f"«{escape(name)}» добавлен в каталог. "
            "Теперь его можно выбрать при создании работы."
        )
        await self._send(int(requested_by), text)

    async def notify_rejected(
        self,
        *,
        requested_by: UserId,
        name: str,
        reason: str | None,
    ) -> None:
        lines = [
            "❌ <b>Заявка отклонена</b>",
            "",
            f"«{escape(name)}» не добавлен в каталог.",
        ]
        if reason:
            lines.append("")
            lines.append("Причина:")
            lines.append(escape(reason))
        await self._send(int(requested_by), "\n".join(lines))

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except TelegramAPIError as e:
            log.warning("fandom_proposal_notify_failed user_id=%s err=%r", chat_id, e)
