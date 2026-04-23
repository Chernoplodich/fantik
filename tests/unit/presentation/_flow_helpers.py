"""Хелперы для тестов FSM-хендлеров: in-memory FSMContext + stub-сообщения."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage


def unwrap(fn: Any) -> Callable[..., Any]:
    """Вернуть оригинальную функцию хэндлера без dishka-`@inject`.

    Dishka хранит её в `__dishka_orig_func__` — этим обходим требование
    `dishka_container` в kwargs при прямом вызове в тестах.
    """
    return getattr(fn, "__dishka_orig_func__", fn)


def make_state(*, user_id: int = 1, chat_id: int = 1) -> FSMContext:
    """Чистый `FSMContext` на `MemoryStorage` для одного юзера."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=0, chat_id=chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


def make_message(text: str | None = None, user_id: int = 1) -> AsyncMock:
    """Минимальный stub `aiogram.types.Message`.

    Содержит `.text`, `.from_user.id`, AsyncMock-методы `.answer(...)`.
    """
    msg = AsyncMock()
    msg.text = text
    msg.entities = None
    msg.photo = None
    from_user = MagicMock()
    from_user.id = user_id
    msg.from_user = from_user
    return msg


def make_callback(
    data: str = "",
    user_id: int = 1,
    with_message: bool = True,
) -> AsyncMock:
    """Минимальный stub `aiogram.types.CallbackQuery`."""
    cb = AsyncMock()
    cb.data = data
    from_user = MagicMock()
    from_user.id = user_id
    cb.from_user = from_user
    if with_message:
        cb.message = AsyncMock()
    else:
        cb.message = None
    return cb


async def answer_texts(mock_answer: Any) -> list[str]:
    """Собрать все позиционные/именованные `text`-аргументы вызовов `.answer()`."""
    texts: list[str] = []
    for call in mock_answer.call_args_list:
        if call.args:
            texts.append(str(call.args[0]))
        elif "text" in call.kwargs:
            texts.append(str(call.kwargs["text"]))
    return texts
