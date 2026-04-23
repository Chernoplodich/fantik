"""NotificationRepository: append-only журнал доставленных уведомлений."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.subscriptions.ports import INotificationRepository
from app.domain.shared.types import NotificationId, UserId
from app.infrastructure.db.models.notification import Notification as NotificationModel


class NotificationRepository(INotificationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        user_id: UserId,
        kind: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> NotificationId:
        m = NotificationModel(
            user_id=int(user_id),
            kind=kind,
            payload=dict(payload),
            created_at=now,
        )
        self._s.add(m)
        await self._s.flush()
        return NotificationId(int(m.id))

    async def create_many(
        self,
        *,
        user_ids: list[UserId],
        kind: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> list[NotificationId]:
        if not user_ids:
            return []
        rows = [
            {
                "user_id": int(uid),
                "kind": kind,
                "payload": dict(payload),
                "created_at": now,
            }
            for uid in user_ids
        ]
        stmt = insert(NotificationModel).returning(NotificationModel.id)
        result = await self._s.execute(stmt, rows)
        await self._s.flush()
        ids = [NotificationId(int(r)) for r in result.scalars().all()]
        return ids

    async def mark_sent(self, *, notification_id: NotificationId, now: datetime) -> None:
        stmt = (
            update(NotificationModel)
            .where(NotificationModel.id == int(notification_id))
            .values(sent_at=now)
        )
        await self._s.execute(stmt)
        await self._s.flush()
