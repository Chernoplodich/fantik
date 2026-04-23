"""Моды получают прямое сообщение о новой подаче — fanout по списку staff-юзеров."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.moderation.ports import IModeratorNotifier
from app.application.users.ports import IUserRepository
from app.domain.shared.types import FanficId, ModerationCaseId, UserId

log = logging.getLogger(__name__)

KIND_LABELS: dict[str, str] = {
    "fic_first_publish": "Первая публикация",
    "fic_edit": "Правка опубликованной работы",
    "chapter_add": "Добавлена глава",
    "chapter_edit": "Правка главы",
}


class ModeratorNotifier(IModeratorNotifier):
    """Отправляет в личку каждому staff-юзеру (admin/moderator).

    Фейл одного получателя не ломает остальных.
    """

    def __init__(self, bot: Bot, users: IUserRepository) -> None:
        self._bot = bot
        self._users = users

    async def notify_new_case(
        self,
        *,
        case_id: ModerationCaseId,
        kind: str,
        fic_id: FanficId,
        fic_title: str,
        author_id: UserId,
    ) -> None:
        staff = await self._users.list_staff()
        if not staff:
            return

        author = await self._users.get(author_id)
        author_parts: list[str] = []
        if author and author.author_nick:
            author_parts.append(f"<b>{escape(str(author.author_nick))}</b>")
        if author and author.username:
            author_parts.append(f"(@{escape(author.username)})")
        author_parts.append(f'<a href="tg://user?id={int(author_id)}">id{int(author_id)}</a>')
        author_line = " ".join(author_parts)

        text = (
            f"🆕 <b>Новое задание на модерацию #{int(case_id)}</b>\n"
            f"Тип: {KIND_LABELS.get(kind, kind)}\n"
            f"Работа: <b>{escape(fic_title)}</b>\n"
            f"Автор: {author_line}\n\n"
            "Открой панель модерации и возьми задание."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛡 Открыть модерацию", callback_data="menu:mod")]
            ]
        )

        for mod_id in staff:
            # не дёргаем самого автора, если он вдруг мод/админ — ему ничего не скажет pick_next
            if mod_id == author_id:
                continue
            try:
                await self._bot.send_message(
                    chat_id=int(mod_id),
                    text=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except TelegramAPIError as e:
                log.warning("mod_notify_failed user_id=%s err=%r", int(mod_id), e)
