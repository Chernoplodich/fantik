"""BroadcastRepository + DeliveryRepository."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.broadcasts.ports import (
    Delivery,
    IBroadcastRepository,
    IDeliveryRepository,
)
from app.domain.broadcasts.entities import Broadcast
from app.domain.broadcasts.value_objects import BroadcastStatus, DeliveryStatus
from app.domain.shared.types import BroadcastId, UserId
from app.infrastructure.db.models.broadcast import (
    Broadcast as BroadcastModel,
)
from app.infrastructure.db.models.broadcast import (
    BroadcastDelivery as DeliveryModel,
)


def _model_to_domain(m: BroadcastModel) -> Broadcast:
    bc = Broadcast(
        id=BroadcastId(int(m.id)),
        created_by=UserId(int(m.created_by)),
        source_chat_id=int(m.source_chat_id),
        source_message_id=int(m.source_message_id),
        keyboard=list(m.keyboard) if m.keyboard else None,
        segment_spec=dict(m.segment_spec or {}),
        scheduled_at=m.scheduled_at,
        status=BroadcastStatus(m.status.value if hasattr(m.status, "value") else m.status),
        stats=dict(m.stats or {}),
        started_at=m.started_at,
        finished_at=m.finished_at,
        created_at=m.created_at,
    )
    # pull_events пуст — сущность из БД, без накопленных событий
    bc.pull_events()
    return bc


def _apply_domain_to_model(m: BroadcastModel, b: Broadcast) -> None:
    m.created_by = int(b.created_by)
    m.source_chat_id = int(b.source_chat_id)
    m.source_message_id = int(b.source_message_id)
    m.keyboard = list(b.keyboard) if b.keyboard is not None else None
    m.segment_spec = dict(b.segment_spec)
    m.scheduled_at = b.scheduled_at
    m.status = b.status
    m.stats = dict(b.stats)
    m.started_at = b.started_at
    m.finished_at = b.finished_at


class BroadcastRepository(IBroadcastRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, broadcast: Broadcast) -> BroadcastId:
        m = BroadcastModel(
            created_by=int(broadcast.created_by),
            source_chat_id=int(broadcast.source_chat_id),
            source_message_id=int(broadcast.source_message_id),
            keyboard=list(broadcast.keyboard) if broadcast.keyboard else None,
            segment_spec=dict(broadcast.segment_spec),
            scheduled_at=broadcast.scheduled_at,
            status=broadcast.status,
            stats=dict(broadcast.stats),
            started_at=broadcast.started_at,
            finished_at=broadcast.finished_at,
            created_at=broadcast.created_at,
        )
        self._s.add(m)
        await self._s.flush()
        return BroadcastId(int(m.id))

    async def get(self, broadcast_id: BroadcastId) -> Broadcast | None:
        m = await self._s.get(BroadcastModel, int(broadcast_id))
        return _model_to_domain(m) if m else None

    async def save(self, broadcast: Broadcast) -> None:
        m = await self._s.get(BroadcastModel, int(broadcast.id))
        if m is None:
            raise LookupError(f"Broadcast #{int(broadcast.id)} not found for save().")
        _apply_domain_to_model(m, broadcast)
        await self._s.flush()

    async def list_by_creator(
        self, *, created_by: UserId, limit: int = 20
    ) -> list[Broadcast]:
        stmt = (
            select(BroadcastModel)
            .where(BroadcastModel.created_by == int(created_by))
            .order_by(BroadcastModel.created_at.desc())
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_model_to_domain(r) for r in rows]

    async def list_by_status(
        self, statuses: list[BroadcastStatus], limit: int = 100
    ) -> list[Broadcast]:
        if not statuses:
            return []
        stmt = (
            select(BroadcastModel)
            .where(BroadcastModel.status.in_([s.value for s in statuses]))
            .order_by(BroadcastModel.created_at.desc())
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_model_to_domain(r) for r in rows]

    async def scan_ready_to_run(
        self, *, now: datetime, limit: int = 10
    ) -> list[BroadcastId]:
        """Атомарно взять scheduled-рассылки, перевести в running.

        CTE + SKIP LOCKED: параллельные scheduler-тики не возьмут одну и ту же.
        """
        stmt = text(
            """
            WITH picked AS (
                SELECT id
                  FROM broadcasts
                 WHERE status = 'scheduled'
                   AND scheduled_at IS NOT NULL
                   AND scheduled_at <= :now
                 ORDER BY scheduled_at
                 FOR UPDATE SKIP LOCKED
                 LIMIT :lim
            )
            UPDATE broadcasts
               SET status = 'running',
                   started_at = :now
             WHERE id IN (SELECT id FROM picked)
             RETURNING id
            """
        )
        rows = await self._s.execute(stmt, {"now": now, "lim": limit})
        return [BroadcastId(int(r[0])) for r in rows.all()]

    async def update_stats(
        self, *, broadcast_id: BroadcastId, stats: dict[str, int]
    ) -> None:
        m = await self._s.get(BroadcastModel, int(broadcast_id))
        if m is None:
            return
        m.stats = dict(stats)


class DeliveryRepository(IDeliveryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert_pending(
        self, *, broadcast_id: BroadcastId, user_ids: list[UserId]
    ) -> int:
        if not user_ids:
            return 0
        rows = [
            {"broadcast_id": int(broadcast_id), "user_id": int(uid), "status": "pending"}
            for uid in user_ids
        ]
        stmt = (
            pg_insert(DeliveryModel)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["broadcast_id", "user_id"])
        )
        result = await self._s.execute(stmt)
        # rowcount есть на CursorResult, мы возвращаем кол-во реально вставленных
        # строк для мониторинга прогресса рассылки.
        return int(getattr(result, "rowcount", 0) or 0)

    async def get_for_update(
        self, *, broadcast_id: BroadcastId, user_id: UserId
    ) -> Delivery | None:
        stmt = (
            select(DeliveryModel)
            .where(
                DeliveryModel.broadcast_id == int(broadcast_id),
                DeliveryModel.user_id == int(user_id),
            )
            .with_for_update()
        )
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        if m is None:
            return None
        return self._to_domain(m)

    async def save(self, delivery: Delivery) -> None:
        stmt = (
            select(DeliveryModel)
            .where(
                DeliveryModel.broadcast_id == int(delivery.broadcast_id),
                DeliveryModel.user_id == int(delivery.user_id),
            )
        )
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        if m is None:
            return
        m.status = delivery.status
        m.attempts = int(delivery.attempts)
        m.error_code = delivery.error_code
        m.sent_at = delivery.sent_at

    async def count_by_status(
        self, broadcast_id: BroadcastId
    ) -> dict[DeliveryStatus, int]:
        stmt = text(
            """
            SELECT status, count(*)
              FROM broadcast_deliveries
             WHERE broadcast_id = :bid
             GROUP BY status
            """
        )
        rows = await self._s.execute(stmt, {"bid": int(broadcast_id)})
        out: dict[DeliveryStatus, int] = dict.fromkeys(
            (
                DeliveryStatus.PENDING,
                DeliveryStatus.SENT,
                DeliveryStatus.FAILED,
                DeliveryStatus.BLOCKED,
            ),
            0,
        )
        for status_val, count in rows.all():
            out[DeliveryStatus(str(status_val))] = int(count)
        return out

    async def iter_user_ids_by_status(
        self,
        *,
        broadcast_id: BroadcastId,
        statuses: list[DeliveryStatus],
        chunk_size: int = 1000,
    ) -> AsyncIterator[list[UserId]]:
        if not statuses:
            return
        status_values = [s.value for s in statuses]
        stmt = (
            select(DeliveryModel.user_id)
            .where(
                DeliveryModel.broadcast_id == int(broadcast_id),
                DeliveryModel.status.in_(status_values),
            )
            .order_by(DeliveryModel.user_id)
            .execution_options(yield_per=chunk_size)
        )
        result = await self._s.stream_scalars(stmt)
        async for chunk in result.partitions(chunk_size):
            yield [UserId(int(x)) for x in chunk]

    @staticmethod
    def _to_domain(m: DeliveryModel) -> Delivery:
        return Delivery(
            broadcast_id=BroadcastId(int(m.broadcast_id)),
            user_id=UserId(int(m.user_id)),
            status=DeliveryStatus(m.status.value if hasattr(m.status, "value") else m.status),
            attempts=int(m.attempts or 0),
            error_code=m.error_code,
            sent_at=m.sent_at,
        )
