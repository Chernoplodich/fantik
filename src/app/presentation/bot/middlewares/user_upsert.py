"""Middleware: touch существующего пользователя при каждом апдейте.

ВАЖНО: этот middleware НЕ создаёт пользователя — только обновляет last_seen
и username/имя у уже зарегистрированных. Создание выполняет ТОЛЬКО
роутер `/start` через `RegisterUserUseCase`. Это гарантирует, что:

- UTM-атрибуция first-touch корректно ставится при первичной регистрации
  (юзер не «съедается» middleware'ом до того, как handler /start увидит
  payload `?start=<utm>` и создаст user с правильным `utm_source_code_id`);
- tracking-события `start` / `register` пишутся ровно один раз — при
  истинной первой регистрации, не при каждом апдейте.

Если юзер шлёт что-то ДО первого /start (callback из чужого forward'а
или ручной апдейт через API) — middleware просто пропускает; downstream-
middleware (role/ban_check) дефолтят на USER без записи в БД.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from dishka import AsyncContainer
from dishka.integrations.aiogram import CONTAINER_NAME

from app.application.users.ports import IUserRepository
from app.domain.shared.types import UserId
from app.infrastructure.db.unit_of_work import UnitOfWork

_UPDATE_EVERY_SECONDS = 60  # если last_seen моложе — не дергаем DB


class UserUpsertMiddleware(BaseMiddleware):
    """Touch существующего user'а. Создание — задача `/start` (см. модуль)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user") or getattr(event, "from_user", None)
        if from_user is None or getattr(from_user, "is_bot", False):
            return await handler(event, data)

        container: AsyncContainer | None = data.get(CONTAINER_NAME)
        if container is not None:
            async with container() as req:
                users: IUserRepository = await req.get(IUserRepository)
                uow: UnitOfWork = await req.get(UnitOfWork)
                now = datetime.now(tz=UTC)
                async with uow:
                    existing = await users.get(UserId(from_user.id))
                    if existing is None:
                        # Не создаём — этим займётся /start handler.
                        # Если апдейт пришёл не от /start (любой текст /
                        # callback), просто пропускаем — downstream middleware
                        # умеют работать с user=None.
                        pass
                    elif (
                        existing.last_seen_at is None
                        or (now - existing.last_seen_at).total_seconds() >= _UPDATE_EVERY_SECONDS
                        or existing.username != from_user.username
                    ):
                        existing.touch(
                            now=now,
                            username=from_user.username,
                            first_name=from_user.first_name,
                            last_name=from_user.last_name,
                            language_code=from_user.language_code,
                        )
                        await users.save(existing)
                        await uow.commit()
        return await handler(event, data)
