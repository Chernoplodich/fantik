"""Общие утилиты рендера презентационного слоя.

`display_author_nick`: подставляет «Удалённый пользователь» для анонимизированных
ников (`deleted_xxxxxxxx`, проставляется DeleteUserUseCase), остальные
возвращает как есть.
"""

from __future__ import annotations

DELETED_USER_LABEL = "Удалённый пользователь"
_DELETED_PREFIX = "deleted_"


def is_anonymized_nick(nick: str | None) -> bool:
    return bool(nick and nick.startswith(_DELETED_PREFIX))


def display_author_nick(nick: str | None) -> str | None:
    """None → None (если ник вообще не задан).

    `deleted_xxxxxxxx` → `«Удалённый пользователь»`.
    Всё остальное — как в БД.
    """
    if nick is None:
        return None
    if is_anonymized_nick(nick):
        return DELETED_USER_LABEL
    return nick
