"""PgUserSegmentReader: резолвит SegmentPlan в SELECT по users."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.application.broadcasts.ports import IUserSegmentReader
from app.domain.broadcasts.segment import SegmentPlan
from app.domain.broadcasts.value_objects import (
    SEGMENT_KIND_ACTIVE_SINCE_DAYS,
    SEGMENT_KIND_ALL,
    SEGMENT_KIND_AUTHORS,
    SEGMENT_KIND_SUBSCRIBERS_OF,
    SEGMENT_KIND_UTM,
)
from app.domain.shared.types import UserId
from app.infrastructure.db.models.fanfic import Fanfic
from app.infrastructure.db.models.subscription import Subscription
from app.infrastructure.db.models.tracking import TrackingCode
from app.infrastructure.db.models.user import User


def build_segment_where(plan: SegmentPlan) -> ColumnElement[bool]:
    """Чистая SQL-билдер функция сегмента → WHERE clause по users.

    Исключение banned_at IS NOT NULL добавляется вызывающим (iter_user_ids).
    """
    if plan.kind == SEGMENT_KIND_ALL:
        return User.id.is_not(None)

    if plan.kind == SEGMENT_KIND_ACTIVE_SINCE_DAYS:
        assert plan.days is not None
        return User.last_seen_at > text(
            f"now() - make_interval(days => {int(plan.days)})"
        )

    if plan.kind == SEGMENT_KIND_AUTHORS:
        # Есть хотя бы один approved fanfic у этого юзера.
        author_has_fic = (
            select(Fanfic.id)
            .where(Fanfic.author_id == User.id, Fanfic.status == "approved")
            .exists()
        )
        return and_(User.author_nick.is_not(None), author_has_fic)

    if plan.kind == SEGMENT_KIND_SUBSCRIBERS_OF:
        assert plan.author_id is not None
        sub_exists = (
            select(Subscription.subscriber_id)
            .where(
                Subscription.subscriber_id == User.id,
                Subscription.author_id == int(plan.author_id),
            )
            .exists()
        )
        return sub_exists

    if plan.kind == SEGMENT_KIND_UTM:
        assert plan.utm_code is not None
        code_scalar = (
            select(TrackingCode.id)
            .where(TrackingCode.code == str(plan.utm_code))
            .scalar_subquery()
        )
        return User.utm_source_code_id == code_scalar

    raise ValueError(f"build_segment_where: неподдерживаемый kind={plan.kind!r}")


class PgUserSegmentReader(IUserSegmentReader):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def iter_user_ids(
        self, *, plan: SegmentPlan, chunk_size: int = 1000
    ) -> AsyncIterator[list[UserId]]:
        where_clause = build_segment_where(plan)
        stmt = (
            select(User.id)
            .where(where_clause)
            .where(User.banned_at.is_(None))
            .where(User.blocked_bot_at.is_(None))
            .order_by(User.id)
            .execution_options(yield_per=chunk_size)
        )
        result = await self._s.stream_scalars(stmt)
        async for chunk in result.partitions(chunk_size):
            yield [UserId(int(x)) for x in chunk]
