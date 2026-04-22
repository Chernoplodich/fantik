"""AuthorNotifier: прямая отправка сообщения автору о решении модерации."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity

from app.application.fanfics.ports import IAuthorNotifier
from app.domain.moderation.value_objects import RejectionReason
from app.domain.shared.types import ChapterId, FanficId, UserId

log = logging.getLogger(__name__)


def _to_entities(raw: list[dict[str, Any]] | None) -> list[MessageEntity] | None:
    if not raw:
        return None
    out: list[MessageEntity] = []
    for e in raw:
        try:
            out.append(MessageEntity.model_validate(e))
        except Exception:  # noqa: BLE001
            continue
    return out or None


def _format_reasons(reasons: list[RejectionReason]) -> str:
    return "\n\n".join(f"• <b>{r.title}</b>\n{r.description}" for r in reasons)


class AuthorNotifier(IAuthorNotifier):
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify_approved(
        self, *, author_id: UserId, fic_id: FanficId, fic_title: str
    ) -> None:
        text = f"✅ Твоя работа «{fic_title}» одобрена и опубликована."
        try:
            await self._bot.send_message(chat_id=int(author_id), text=text)
        except TelegramAPIError as e:
            log.warning("notifier_approve_failed user_id=%s err=%r", int(author_id), e)

    async def notify_rejected(
        self,
        *,
        author_id: UserId,
        fic_id: FanficId,
        fic_title: str,
        reasons: list[RejectionReason],
        comment: str | None,
        comment_entities: list[dict[str, Any]],
    ) -> None:
        lines = [
            f"❌ Работа «{fic_title}» отклонена.",
            "",
            "Причины:",
            "\n".join(f"• {r.title} — {r.description}" for r in reasons),
        ]
        if comment:
            lines.append("")
            lines.append("Комментарий модератора:")
            lines.append(comment)

        full_text = "\n".join(lines)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Доработать",
                        callback_data=f"fic:revise:{int(fic_id)}",
                    )
                ]
            ]
        )

        # Entities модератора — не переносим, offset'ы не совпадают с финальным текстом.
        try:
            await self._bot.send_message(
                chat_id=int(author_id),
                text=full_text,
                reply_markup=kb,
            )
        except TelegramAPIError as e:
            log.warning("notifier_reject_failed user_id=%s err=%r", int(author_id), e)

    async def notify_chapter_approved(
        self,
        *,
        author_id: UserId,
        fic_id: FanficId,
        chapter_id: ChapterId,
        chapter_number: int,
        fic_title: str,
    ) -> None:
        text = f"✅ Глава {chapter_number} работы «{fic_title}» одобрена."
        try:
            await self._bot.send_message(chat_id=int(author_id), text=text)
        except TelegramAPIError as e:
            log.warning("notifier_chapter_approve_failed user_id=%s err=%r", int(author_id), e)

    async def notify_chapter_rejected(
        self,
        *,
        author_id: UserId,
        fic_id: FanficId,
        chapter_id: ChapterId,
        chapter_number: int,
        fic_title: str,
        reasons: list[RejectionReason],
        comment: str | None,
        comment_entities: list[dict[str, Any]],
    ) -> None:
        lines = [
            f"❌ Глава {chapter_number} работы «{fic_title}» отклонена.",
            "",
            "Причины:",
            "\n".join(f"• {r.title} — {r.description}" for r in reasons),
        ]
        if comment:
            lines.append("")
            lines.append("Комментарий модератора:")
            lines.append(comment)
        text = "\n".join(lines)
        try:
            await self._bot.send_message(chat_id=int(author_id), text=text)
        except TelegramAPIError as e:
            log.warning(
                "notifier_chapter_reject_failed user_id=%s err=%r", int(author_id), e
            )
