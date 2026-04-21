"""Use case: фиксация согласия с правилами (часть онбординга)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.shared.ports import UnitOfWork
from app.application.users.ports import IUserRepository
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.shared.types import UserId


@dataclass(frozen=True, kw_only=True)
class AgreeToRulesCommand:
    user_id: int


class AgreeToRulesUseCase:
    def __init__(self, uow: UnitOfWork, users: IUserRepository, clock: Clock) -> None:
        self._uow = uow
        self._users = users
        self._clock = clock

    async def __call__(self, cmd: AgreeToRulesCommand) -> None:
        now = self._clock.now()
        async with self._uow:
            user = await self._users.get(UserId(cmd.user_id))
            if user is None:
                raise NotFoundError("Пользователь не найден.")
            user.agree_to_rules(now=now)
            await self._users.save(user)
            await self._uow.commit()
