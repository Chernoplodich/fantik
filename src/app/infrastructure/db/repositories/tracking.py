"""TrackingRepository."""

from __future__ import annotations

from sqlalchemy import exists, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.tracking.ports import ITrackingRepository
from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.tracking.entities import (
    TrackingCode as TrackingCodeEntity,
)
from app.domain.tracking.entities import (
    TrackingEvent as TrackingEventEntity,
)
from app.domain.tracking.value_objects import TrackingCodeStr, TrackingEventType
from app.infrastructure.db.models.tracking import (
    TrackingCode as TrackingCodeModel,
)
from app.infrastructure.db.models.tracking import (
    TrackingEvent as TrackingEventModel,
)


class TrackingRepository(ITrackingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_code_id(self, code: str) -> TrackingCodeId | None:
        stmt = select(TrackingCodeModel.id).where(
            TrackingCodeModel.code == code,
            TrackingCodeModel.active.is_(True),
        )
        val = (await self._s.execute(stmt)).scalar_one_or_none()
        return TrackingCodeId(val) if val is not None else None

    async def get_code(self, code_id: TrackingCodeId) -> TrackingCodeEntity | None:
        m = await self._s.get(TrackingCodeModel, int(code_id))
        if m is None:
            return None
        return _to_domain_code(m)

    async def list_codes(self, *, active_only: bool = False) -> list[TrackingCodeEntity]:
        stmt = select(TrackingCodeModel).order_by(TrackingCodeModel.created_at.desc())
        if active_only:
            stmt = stmt.where(TrackingCodeModel.active.is_(True))
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_domain_code(m) for m in rows]

    async def save_code(self, code: TrackingCodeEntity) -> TrackingCodeEntity:
        model = TrackingCodeModel(
            code=str(code.code),
            name=code.name,
            description=code.description,
            created_by=int(code.created_by),
            active=code.active,
        )
        self._s.add(model)
        await self._s.flush()
        return _to_domain_code(model)

    async def record(self, event: TrackingEventEntity) -> None:
        await self._s.execute(
            insert(TrackingEventModel).values(
                code_id=int(event.code_id) if event.code_id is not None else None,
                user_id=int(event.user_id),
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
        )

    async def has_event_for_user(self, user_id: UserId, event_type: str) -> bool:
        stmt = select(
            exists().where(
                TrackingEventModel.user_id == int(user_id),
                TrackingEventModel.event_type == event_type,
            )
        )
        return bool((await self._s.execute(stmt)).scalar_one())


def _to_domain_code(m: TrackingCodeModel) -> TrackingCodeEntity:
    return TrackingCodeEntity(
        id=TrackingCodeId(m.id),
        code=TrackingCodeStr(m.code),
        name=m.name,
        description=m.description,
        created_by=UserId(m.created_by) if m.created_by else UserId(0),
        active=m.active,
        created_at=m.created_at,
    )


# Re-export чтобы доменный TrackingEventType не ломал импорты снаружи.
__all__ = ["TrackingEventType", "TrackingRepository"]
