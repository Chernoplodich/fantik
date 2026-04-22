"""Валидатор Telegram MessageEntities.

Принимает список dict'ов в формате Telegram API, возвращает очищенный
и отсортированный список (JSONB-готовый) или поднимает InvalidEntityError.

Инварианты:
- Разрешённые типы (whitelist): bold, italic, underline, strikethrough,
  spoiler, code, pre, blockquote, expandable_blockquote, text_link,
  custom_emoji, url, email, phone_number, mention, hashtag, cashtag,
  bot_command.
- Запрещён `text_mention` (MVP: приватность + невалидное поле `user`
  после форварда).
- text_link.url — только схемы http, https, tg, mailto.
- custom_emoji обязан содержать custom_emoji_id.
- offset ≥ 0, length ≥ 1, offset + length ≤ utf16_length(text).
- Не более MAX_ENTITIES_PER_TEXT entities (1000).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.domain.fanfics.exceptions import InvalidEntityError
from app.domain.fanfics.value_objects import MAX_ENTITIES_PER_TEXT
from app.domain.shared.utf16 import utf16_length

ALLOWED_TYPES: frozenset[str] = frozenset({
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "spoiler",
    "code",
    "pre",
    "blockquote",
    "expandable_blockquote",
    "text_link",
    "custom_emoji",
    "url",
    "email",
    "phone_number",
    "mention",
    "hashtag",
    "cashtag",
    "bot_command",
})

ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https", "tg", "mailto"})


def _validate_one(e: dict[str, Any], text_u16_len: int) -> dict[str, Any]:
    if not isinstance(e, dict):
        raise InvalidEntityError("entity must be an object")

    t = e.get("type")
    if not isinstance(t, str):
        raise InvalidEntityError("entity.type must be a string")
    if t == "text_mention":
        raise InvalidEntityError(
            "text_mention не допускается в MVP (приватность)."
        )
    if t not in ALLOWED_TYPES:
        raise InvalidEntityError(f"entity type {t!r} не разрешён")

    offset = e.get("offset")
    length = e.get("length")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise InvalidEntityError("entity.offset must be non-negative int")
    if not isinstance(length, int) or isinstance(length, bool) or length < 1:
        raise InvalidEntityError("entity.length must be positive int")
    if offset + length > text_u16_len:
        raise InvalidEntityError(
            f"entity out of bounds (offset={offset}, length={length}, text_u16={text_u16_len})"
        )

    out: dict[str, Any] = {"type": t, "offset": offset, "length": length}

    if t == "text_link":
        url = e.get("url")
        if not isinstance(url, str) or not url:
            raise InvalidEntityError("text_link.url required")
        try:
            scheme = urlparse(url).scheme.lower()
        except ValueError as exc:
            raise InvalidEntityError(f"text_link.url is not a valid URL: {url!r}") from exc
        if scheme not in ALLOWED_URL_SCHEMES:
            raise InvalidEntityError(
                f"text_link.url scheme {scheme!r} запрещена "
                f"(разрешены: {sorted(ALLOWED_URL_SCHEMES)})."
            )
        out["url"] = url

    elif t == "custom_emoji":
        cid = e.get("custom_emoji_id")
        if not isinstance(cid, str) or not cid:
            raise InvalidEntityError("custom_emoji.custom_emoji_id required")
        out["custom_emoji_id"] = cid

    elif t == "pre":
        lang = e.get("language")
        if lang is not None:
            if not isinstance(lang, str) or len(lang) > 64:
                raise InvalidEntityError("pre.language must be string ≤ 64 chars")
            out["language"] = lang

    return out


def validate(text: str, entities: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Вернуть очищенный отсортированный список entities или поднять.

    Пустой/None на входе — пустой список на выходе.
    """
    if not entities:
        return []
    if len(entities) > MAX_ENTITIES_PER_TEXT:
        raise InvalidEntityError(
            f"Слишком много форматирующих entities (>{MAX_ENTITIES_PER_TEXT})."
        )

    text_u16 = utf16_length(text)
    cleaned: list[dict[str, Any]] = [_validate_one(e, text_u16) for e in entities]
    cleaned.sort(key=lambda e: (e["offset"], -e["length"]))
    return cleaned
