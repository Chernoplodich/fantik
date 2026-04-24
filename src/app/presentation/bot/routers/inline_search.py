"""Inline-режим поиска: `@bot <query>`.

- Нормализация запроса → ключ в Redis-кэше (TTL 60с).
- Пустой запрос → топ-10 самых популярных (кэшируется отдельно).
- Результат с обложкой → `InlineQueryResultCachedPhoto` (карточка-фото).
- Результат без обложки → `InlineQueryResultArticle` (текстовая карточка).
- Все кнопки — deep-link `t.me/<bot>?start=fic_<id>`.
"""

from __future__ import annotations

import re

from aiogram import Bot, Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
)
from dishka.integrations.aiogram import FromDishka, inject

from app.application.search.dto import SearchCommand, SearchHit
from app.application.search.ports import ISearchCache
from app.application.search.search import SearchUseCase
from app.core.logging import get_logger

log = get_logger(__name__)
router = Router(name="inline_search")

_CACHE_TTL_S = 60
_INLINE_LIMIT = 20
_NORMALIZE_RE = re.compile(r"\s+")
_EMPTY_KEY = "inline:__empty__"
# Лимит caption у Telegram InlineQueryResultCachedPhoto — 1024 символа.
_PHOTO_CAPTION_LIMIT = 1000


def _normalize(q: str) -> str:
    return _NORMALIZE_RE.sub(" ", q.strip().lower())


def _cache_key(norm: str) -> str:
    return _EMPTY_KEY if not norm else f"inline:{norm}"


def _hit_to_raw(h: SearchHit) -> dict[str, object]:
    """Сериализуем SearchHit в dict для msgpack-кэша."""
    return {
        "fic_id": int(h.fic_id),
        "title": str(h.title),
        "author_nick": h.author_nick or "",
        "fandom_name": h.fandom_name or "",
        "age_rating": str(h.age_rating),
        "likes_count": int(h.likes_count),
        "cover_file_id": h.cover_file_id or "",
    }


def _build_texts(raw: dict[str, object]) -> tuple[str, str, str]:
    """Возвращает (title, description, message_text)."""
    from app.presentation.bot.display import display_author_nick

    fic_id = int(raw.get("fic_id", 0) or 0)
    title = str(raw.get("title") or "") or f"Работа #{fic_id}"
    author = display_author_nick(str(raw.get("author_nick") or "") or None) or ""
    fandom = str(raw.get("fandom_name") or "")
    age = str(raw.get("age_rating") or "")
    likes = int(raw.get("likes_count", 0) or 0)

    desc_parts: list[str] = []
    if author:
        desc_parts.append(author)
    if fandom:
        desc_parts.append(fandom)
    if age:
        desc_parts.append(age)
    desc_parts.append(f"❤️ {likes}")
    description = " · ".join(desc_parts)

    msg_parts = [f"📖 *{title}*"]
    if author:
        msg_parts.append(f"Автор: {author}")
    if fandom:
        msg_parts.append(f"Фэндом: {fandom}")
    if age:
        msg_parts.append(f"Возраст: {age}")
    msg_parts.append(f"❤️ {likes}")
    msg_text = "\n".join(msg_parts)

    return title, description, msg_text


def _read_button(bot_username: str, fic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Читать",
                    url=f"https://t.me/{bot_username}?start=fic_{fic_id}",
                )
            ]
        ]
    )


def _raw_to_result(
    raw: dict[str, object], bot_username: str
) -> InlineQueryResultArticle | InlineQueryResultCachedPhoto:
    fic_id = int(raw.get("fic_id", 0) or 0)
    title, description, msg_text = _build_texts(raw)
    kb = _read_button(bot_username, fic_id)
    cover = str(raw.get("cover_file_id") or "")

    if cover:
        # Фото-карточка: в caption сразу видно мета-строку и можно делить (Markdown).
        caption = msg_text[:_PHOTO_CAPTION_LIMIT]
        return InlineQueryResultCachedPhoto(
            id=str(fic_id),
            photo_file_id=cover,
            title=title,
            description=description,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=kb,
        )

    # Без обложки — обычная текстовая карточка.
    return InlineQueryResultArticle(
        id=str(fic_id),
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=msg_text,
            parse_mode="Markdown",
        ),
        reply_markup=kb,
    )


@router.inline_query()
@inject
async def inline_search(
    iq: InlineQuery,
    bot: FromDishka[Bot],
    search_uc: FromDishka[SearchUseCase],
    cache: FromDishka[ISearchCache],
) -> None:
    norm = _normalize(iq.query or "")
    key = _cache_key(norm)

    cached = await cache.get(key)
    if isinstance(cached, list):
        raws = [r for r in cached if isinstance(r, dict)]
    else:
        # «Без запроса» = топ по лайкам. Пустой q в fallback_pg тоже теперь
        # возвращает топ (см. fallback_pg.py) — консистентно с Meili.
        cmd = SearchCommand(
            q=norm,
            sort="top" if not norm else "relevance",
            limit=_INLINE_LIMIT,
            offset=0,
        )
        result = await search_uc(cmd)
        raws = [_hit_to_raw(h) for h in result.hits]
        await cache.setex(key, _CACHE_TTL_S, raws)

    me = await bot.me()
    username = me.username or "bot"
    results = [_raw_to_result(raw, username) for raw in raws]

    await iq.answer(
        results=results,
        cache_time=_CACHE_TTL_S,
        is_personal=False,
    )
