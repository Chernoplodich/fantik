"""Use case: пользователь отписывается от автора фика."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IFanficRepository
from app.application.shared.ports import UnitOfWork
from app.application.subscriptions.ports import ISubscriptionRepository
from app.core.errors import NotFoundError
from app.domain.shared.types import FanficId, UserId
from app.domain.subscriptions.events import UserUnsubscribedFromAuthor


@dataclass(frozen=True, kw_only=True)
class UnsubscribeCommand:
    subscriber_id: int
    fic_id: int


@dataclass(frozen=True, kw_only=True)
class UnsubscribeResult:
    author_id: UserId
    removed: bool


class UnsubscribeUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        subscriptions: ISubscriptionRepository,
        fanfics: IFanficRepository,
    ) -> None:
        self._uow = uow
        self._subs = subscriptions
        self._fanfics = fanfics

    async def __call__(self, cmd: UnsubscribeCommand) -> UnsubscribeResult:
        subscriber_id = UserId(cmd.subscriber_id)
        async with self._uow:
            fic = await self._fanfics.get(FanficId(cmd.fic_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            author_id = fic.author_id
            removed = await self._subs.remove(subscriber_id=subscriber_id, author_id=author_id)
            if removed:
                self._uow.record_events(
                    [UserUnsubscribedFromAuthor(subscriber_id=subscriber_id, author_id=author_id)]
                )
            await self._uow.commit()
            return UnsubscribeResult(author_id=author_id, removed=removed)
