"""AuditLogRepository: запись решений модератора и других действий."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.moderation.ports import IAuditLog
from app.domain.shared.types import AuditLogId, UserId
from app.infrastructure.db.models.audit_log import AuditLog as AuditLogModel


class AuditLogRepository(IAuditLog):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def log(
        self,
        *,
        actor_id: UserId | None,
        action: str,
        target_type: str,
        target_id: int,
        payload: dict[str, Any],
        now: datetime,
    ) -> AuditLogId:
        m = AuditLogModel(
            actor_id=int(actor_id) if actor_id is not None else None,
            action=action,
            target_type=target_type,
            target_id=int(target_id),
            payload=dict(payload),
            created_at=now,
        )
        self._s.add(m)
        await self._s.flush()
        return AuditLogId(int(m.id))
