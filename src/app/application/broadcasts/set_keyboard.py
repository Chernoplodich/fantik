"""Use case: задать/очистить inline-клавиатуру рассылки.

Принимает текстовый wizard-ввод формата:
    текст|https://...
    текст2|tg://...
    -----               <-- пустая строка или '---' = разделитель рядов

Или None, если кнопок нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.application.broadcasts.ports import IBroadcastRepository
from app.application.shared.ports import UnitOfWork
from app.core.errors import NotFoundError
from app.domain.broadcasts.exceptions import KeyboardValidationError
from app.domain.shared.types import BroadcastId


@dataclass(frozen=True, kw_only=True)
class SetKeyboardCommand:
    broadcast_id: int
    # либо готовая структура (list[list[dict]]), либо raw-текст, либо None.
    keyboard: list[list[dict[str, Any]]] | None = None
    raw_text: str | None = None


_ALLOWED_SCHEMES = frozenset({"https", "tg", "http"})
_MAX_BUTTONS = 64
_MAX_TEXT_LEN = 64
_MAX_URL_LEN = 256


def parse_keyboard_text(raw: str) -> list[list[dict[str, Any]]] | None:
    """Распарсить wizard-ввод в структуру InlineKeyboardMarkup.inline_keyboard.

    Валидирует: пустую строку = разделитель рядов; «текст|url» — одна кнопка;
    URL должен начинаться с https://, tg://, t.me/.
    """
    rows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    total_buttons = 0

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line in {"---", "----"}:
            if current:
                rows.append(current)
                current = []
            continue
        if "|" not in line:
            raise KeyboardValidationError(
                f"Строка «{line}» не содержит разделитель «|»."
            )
        text, url = (x.strip() for x in line.split("|", 1))
        if not text:
            raise KeyboardValidationError("Пустой текст кнопки.")
        if len(text) > _MAX_TEXT_LEN:
            raise KeyboardValidationError(
                f"Текст кнопки длиннее {_MAX_TEXT_LEN} символов: «{text}»."
            )
        _validate_url(url)
        if len(url) > _MAX_URL_LEN:
            raise KeyboardValidationError(f"URL длиннее {_MAX_URL_LEN}: «{url}».")
        current.append({"text": text, "url": url})
        total_buttons += 1
        if total_buttons > _MAX_BUTTONS:
            raise KeyboardValidationError(
                f"Слишком много кнопок, максимум {_MAX_BUTTONS}."
            )

    if current:
        rows.append(current)
    if not rows:
        return None
    return rows


def _validate_url(url: str) -> None:
    if not url:
        raise KeyboardValidationError("Пустой URL кнопки.")
    if url.startswith("t.me/"):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise KeyboardValidationError(
            f"Недопустимая схема URL «{parsed.scheme}» — разрешены "
            "https://, tg://, t.me/."
        )
    if not parsed.netloc and parsed.scheme != "tg":
        raise KeyboardValidationError(f"URL без хоста: «{url}».")


class SetKeyboardUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        broadcasts: IBroadcastRepository,
    ) -> None:
        self._uow = uow
        self._broadcasts = broadcasts

    async def __call__(self, cmd: SetKeyboardCommand) -> None:
        async with self._uow:
            bc = await self._broadcasts.get(BroadcastId(int(cmd.broadcast_id)))
            if bc is None:
                raise NotFoundError("Рассылка не найдена.")

            if cmd.raw_text is not None:
                keyboard = parse_keyboard_text(cmd.raw_text)
            else:
                keyboard = cmd.keyboard

            bc.set_keyboard(keyboard)
            await self._broadcasts.save(bc)
            await self._uow.commit()
