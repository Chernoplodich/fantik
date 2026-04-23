"""Use case: пользователь подписывается на автора фика."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IFanficRepository
from app.application.shared.ports import UnitOfWork
from app.application.subscriptions.ports import ISubscriptionRepository
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.shared.types import FanficId, UserId
from app.domain.subscriptions.events import UserSubscribedToAuthor
from app.domain.subscriptions.exceptions import SelfSubscribeError


@dataclass(frozen=True, kw_only=True)
class SubscribeCommand:
    subscriber_id: int
    fic_id: int  # берём автора из фика, чтобы UI не гонял лишние id


@dataclass(frozen=True, kw_only=True)
class SubscribeResult:
    author_id: UserId
    created: bool  # False если подписка уже была (идемпотентность)


class SubscribeUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        subscriptions: ISubscriptionRepository,
        fanfics: IFanficRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._subs = subscriptions
        self._fanfics = fanfics
        self._clock = clock

    async def __call__(self, cmd: SubscribeCommand) -> SubscribeResult:
        subscriber_id = UserId(cmd.subscriber_id)
        async with self._uow:
            fic = await self._fanfics.get(FanficId(cmd.fic_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            author_id = fic.author_id
            if subscriber_id == author_id:
                raise SelfSubscribeError("Нельзя подписаться на самого себя.")

            created = await self._subs.add_if_absent(
                subscriber_id=subscriber_id,
                author_id=author_id,
                now=self._clock.now(),
            )
            if created:
                self._uow.record_events(
                    [UserSubscribedToAuthor(subscriber_id=subscriber_id, author_id=author_id)]
                )
            await self._uow.commit()
            return SubscribeResult(author_id=author_id, created=created)
