"""ModerationRepository: очередь с SKIP LOCKED + idempotent decision."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.moderation.ports import IModerationRepository
from app.domain.fanfics.value_objects import MqKind
from app.domain.moderation.entities import ModerationCase
from app.domain.moderation.events import (
    ModerationCaseCreated,
    ModerationCaseUnlocked,
)
from app.domain.shared.types import (
    ChapterId,
    FanficId,
    ModerationCaseId,
    UserId,
)
from app.infrastructure.db.mappers.moderation import (
    apply_mq_to_model,
    mq_to_domain,
)
from app.infrastructure.db.models.moderation_queue import (
    ModerationQueue as MQModel,
)


class ModerationRepository(IModerationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_case(
        self,
        *,
        fic_id: FanficId,
        chapter_id: ChapterId | None,
        kind: MqKind,
        submitted_by: UserId,
        now: datetime,
    ) -> ModerationCase:
        m = MQModel(
            fic_id=int(fic_id),
            chapter_id=int(chapter_id) if chapter_id is not None else None,
            kind=kind,
            submitted_by=int(submitted_by),
            submitted_at=now,
        )
        self._s.add(m)
        await self._s.flush()
        case = mq_to_domain(m)
        case._emit(  # type: ignore[attr-defined]
            ModerationCaseCreated(
                case_id=case.id,
                fic_id=case.fic_id,
                chapter_id=case.chapter_id,
                kind=str(kind),
                submitted_by=submitted_by,
            )
        )
        return case

    async def get_by_id(
        self, case_id: ModerationCaseId
    ) -> ModerationCase | None:
        row = await self._s.get(MQModel, int(case_id))
        return mq_to_domain(row) if row else None

    async def get_open_by_fic(self, fic_id: FanficId) -> ModerationCase | None:
        stmt = (
            select(MQModel)
            .where(
                MQModel.fic_id == int(fic_id),
                MQModel.decision.is_(None),
                MQModel.cancelled_at.is_(None),
            )
            .order_by(MQModel.submitted_at.desc())
            .limit(1)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return mq_to_domain(row) if row else None

    async def pick_next(
        self, *, moderator_id: UserId, now: datetime
    ) -> ModerationCase | None:
        # CTE + FOR UPDATE SKIP LOCKED + UPDATE RETURNING
        sql = text(
            """
            WITH next AS (
                SELECT id FROM moderation_queue
                 WHERE decision IS NULL
                   AND cancelled_at IS NULL
                   AND (locked_until IS NULL OR locked_until < :now)
                   AND submitted_by <> :moderator_id
                 ORDER BY submitted_at
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1
            )
            UPDATE moderation_queue mq
               SET locked_by = :moderator_id,
                   locked_until = :now + INTERVAL '15 minutes'
              FROM next
             WHERE mq.id = next.id
            RETURNING mq.id
            """
        )
        result = await self._s.execute(
            sql, {"moderator_id": int(moderator_id), "now": now}
        )
        row = result.first()
        if row is None:
            return None
        case_id = int(row.id)
        row_m = await self._s.get(MQModel, case_id)
        if row_m is None:
            return None
        return mq_to_domain(row_m)

    async def save_decision_idempotent(self, case: ModerationCase) -> bool:
        """UPDATE ... WHERE decision IS NULL AND cancelled_at IS NULL."""
        result = await self._s.execute(
            update(MQModel)
            .where(
                MQModel.id == int(case.id),
                MQModel.decision.is_(None),
                MQModel.cancelled_at.is_(None),
            )
            .values(
                decision=case.decision,
                decision_reason_ids=list(case.decision_reason_ids),
                decision_comment=case.decision_comment,
                decision_comment_entities=list(case.decision_comment_entities),
                decided_by=int(case.decided_by) if case.decided_by is not None else None,
                decided_at=case.decided_at,
                locked_by=int(case.locked_by) if case.locked_by is not None else None,
                locked_until=case.locked_until,
            )
        )
        return bool(result.rowcount)

    async def unlock(
        self, *, case_id: ModerationCaseId, moderator_id: UserId
    ) -> bool:
        result = await self._s.execute(
            update(MQModel)
            .where(
                MQModel.id == int(case_id),
                MQModel.locked_by == int(moderator_id),
                MQModel.decision.is_(None),
                MQModel.cancelled_at.is_(None),
            )
            .values(locked_by=None, locked_until=None)
        )
        return bool(result.rowcount)

    async def release_stale_locks(self, *, now: datetime) -> int:
        result = await self._s.execute(
            update(MQModel)
            .where(
                MQModel.decision.is_(None),
                MQModel.cancelled_at.is_(None),
                MQModel.locked_until.is_not(None),
                MQModel.locked_until < now,
            )
            .values(locked_by=None, locked_until=None)
        )
        return int(result.rowcount or 0)

    async def mark_cancelled(
        self, *, case_id: ModerationCaseId, now: datetime
    ) -> bool:
        result = await self._s.execute(
            update(MQModel)
            .where(
                MQModel.id == int(case_id),
                MQModel.decision.is_(None),
                MQModel.cancelled_at.is_(None),
            )
            .values(cancelled_at=now, locked_by=None, locked_until=None)
        )
        return bool(result.rowcount)
