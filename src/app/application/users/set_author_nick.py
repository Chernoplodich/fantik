"""Use case: установка ника автора."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.shared.ports import UnitOfWork
from app.application.users.ports import IUserRepository
from app.core.errors import NotFoundError
from app.domain.shared.types import UserId
from app.domain.users.exceptions import AuthorNickAlreadyTakenError
from app.domain.users.value_objects import AuthorNick


@dataclass(frozen=True, kw_only=True)
class SetAuthorNickCommand:
    user_id: int
    nick: str


@dataclass(frozen=True, kw_only=True)
class SetAuthorNickResult:
    nick: str


class SetAuthorNickUseCase:
    def __init__(self, uow: UnitOfWork, users: IUserRepository) -> None:
        self._uow = uow
        self._users = users

    async def __call__(self, cmd: SetAuthorNickCommand) -> SetAuthorNickResult:
        nick = AuthorNick(cmd.nick)
        async with self._uow:
            user = await self._users.get(UserId(cmd.user_id))
            if user is None:
                raise NotFoundError("Пользователь не найден.")
            taken = await self._users.is_nick_taken(nick.lowered, except_user_id=user.id)
            if taken:
                raise AuthorNickAlreadyTakenError("Ник уже занят — выбери другой.")
            user.set_author_nick(nick)
            await self._users.save(user)
            self._uow.record_events(user.pull_events())
            await self._uow.commit()
        return SetAuthorNickResult(nick=str(nick))
