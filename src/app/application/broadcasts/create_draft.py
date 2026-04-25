"""Use case: создать draft рассылки (admin отправил шаблон-сообщение)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.broadcasts.ports import IBroadcastRepository
from app.application.fanfics.ports import IOutboxRepository
from app.application.moderation.ports import IAuditLog
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.domain.broadcasts.entities import Broadcast
from app.domain.shared.types import BroadcastId, UserId


@dataclass(frozen=True, kw_only=True)
class CreateBroadcastDraftCommand:
    created_by: int
    source_chat_id: int
    source_message_id: int


@dataclass(frozen=True, kw_only=True)
class CreateBroadcastDraftResult:
    broadcast_id: int


class CreateBroadcastDraftUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        broadcasts: IBroadcastRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._broadcasts = broadcasts
        self._outbox = outbox
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: CreateBroadcastDraftCommand) -> CreateBroadcastDraftResult:
        async with self._uow:
            now = self._clock.now()
            draft = Broadcast.new_draft(
                broadcast_id=BroadcastId(0),  # временный — БД назначит
                created_by=UserId(int(cmd.created_by)),
                source_chat_id=int(cmd.source_chat_id),
                source_message_id=int(cmd.source_message_id),
                now=now,
            )
            new_id = await self._broadcasts.create(draft)
            payload: dict[str, Any] = {
                "broadcast_id": int(new_id),
                "source_chat_id": int(cmd.source_chat_id),
                "source_message_id": int(cmd.source_message_id),
            }
            await self._outbox.append(
                event_type="broadcast.created",
                payload=payload,
                now=now,
            )
            await self._audit.log(
                actor_id=UserId(int(cmd.created_by)),
                action="broadcast.create",
                target_type="broadcast",
                target_id=int(new_id),
                payload=payload,
                now=now,
            )
            await self._uow.commit()
        return CreateBroadcastDraftResult(broadcast_id=int(new_id))
