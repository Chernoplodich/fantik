"""SubscriptionRepository: подписка читателя на автора."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.subscriptions.ports import ISubscriptionRepository
from app.domain.shared.types import UserId
from app.infrastructure.db.models.subscription import Subscription as SubscriptionModel


class SubscriptionRepository(ISubscriptionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_if_absent(
        self, *, subscriber_id: UserId, author_id: UserId, now: datetime
    ) -> bool:
        stmt = (
            pg_insert(SubscriptionModel)
            .values(
                subscriber_id=int(subscriber_id),
                author_id=int(author_id),
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["subscriber_id", "author_id"])
        )
        result = await self._s.execute(stmt)
        await self._s.flush()
        return int(result.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def remove(self, *, subscriber_id: UserId, author_id: UserId) -> bool:
        stmt = delete(SubscriptionModel).where(
            SubscriptionModel.subscriber_id == int(subscriber_id),
            SubscriptionModel.author_id == int(author_id),
        )
        result = await self._s.execute(stmt)
        await self._s.flush()
        return int(result.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def exists(self, *, subscriber_id: UserId, author_id: UserId) -> bool:
        stmt = select(SubscriptionModel.subscriber_id).where(
            SubscriptionModel.subscriber_id == int(subscriber_id),
            SubscriptionModel.author_id == int(author_id),
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def iter_subscriber_ids(
        self, *, author_id: UserId, chunk_size: int = 500
    ) -> AsyncIterator[list[UserId]]:
        """Стримить id подписчиков чанками через keyset-пагинацию по subscriber_id.

        Курсор yield_per можно было бы использовать, но он требует streaming-режима
        AsyncSession, который ломает тестовую транзакцию. Кейсет-пагинация работает
        везде одинаково: последний id → `subscriber_id > last_id` на следующей странице.
        """
        last_id: int | None = None
        while True:
            stmt = select(SubscriptionModel.subscriber_id).where(
                SubscriptionModel.author_id == int(author_id)
            )
            if last_id is not None:
                stmt = stmt.where(SubscriptionModel.subscriber_id > last_id)
            stmt = stmt.order_by(SubscriptionModel.subscriber_id.asc()).limit(chunk_size)
            rows = (await self._s.execute(stmt)).scalars().all()
            if not rows:
                break
            yield [UserId(int(r)) for r in rows]
            last_id = int(rows[-1])
            if len(rows) < chunk_size:
                break
