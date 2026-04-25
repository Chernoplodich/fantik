"""Use cases выгрузки списка id пользователей (admin only).

Используются в админ-панели для двух сценариев:
- общая выгрузка всех зарегистрированных пользователей;
- выгрузка пользователей, пришедших по конкретной UTM-ссылке (first-touch
  атрибуция через `users.utm_source_code_id`).

Каждое действие пишет audit-запись — это PII-выгрузка, должна оставлять след.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.moderation.ports import IAuditLog
from app.application.tracking.ports import ITrackingRepository
from app.application.users.ports import IUserRepository
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.shared.types import TrackingCodeId, UserId


@dataclass(frozen=True, kw_only=True)
class ExportUserIdsCommand:
    actor_id: int


@dataclass(frozen=True, kw_only=True)
class ExportUtmUserIdsCommand:
    actor_id: int
    code_id: int


@dataclass(frozen=True, kw_only=True)
class ExportUserIdsResult:
    """Идентификаторы — int'ы, без user-объектов; вызывающий собирает .txt."""

    user_ids: list[int]
    label: str  # для имени файла / caption: "all" или "utm_<code>"


class ExportAllUserIdsUseCase:
    """Возвращает id всех пользователей (включая banned/blocked_bot)."""

    def __init__(self, users: IUserRepository, audit: IAuditLog, clock: Clock) -> None:
        self._users = users
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: ExportUserIdsCommand) -> ExportUserIdsResult:
        ids = await self._users.list_all_user_ids()
        await self._audit.log(
            actor_id=UserId(int(cmd.actor_id)),
            action="users.export_all",
            target_type="users",
            target_id=0,  # 0 = нет конкретного target (выгрузка всех)
            payload={"count": len(ids)},
            now=self._clock.now(),
        )
        return ExportUserIdsResult(
            user_ids=[int(u) for u in ids],
            label="all",
        )


class ExportUtmUserIdsUseCase:
    """Выгрузка id пользователей с заданной first-touch UTM-кампанией."""

    def __init__(
        self,
        users: IUserRepository,
        tracking: ITrackingRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._users = users
        self._tracking = tracking
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: ExportUtmUserIdsCommand) -> ExportUserIdsResult:
        code_id = TrackingCodeId(int(cmd.code_id))
        code = await self._tracking.get_code(code_id)
        if code is None:
            raise NotFoundError("Трекинговый код не найден.")
        ids = await self._users.list_user_ids_by_utm_code(code_id)
        await self._audit.log(
            actor_id=UserId(int(cmd.actor_id)),
            action="users.export_utm",
            target_type="tracking_code",
            target_id=int(cmd.code_id),
            payload={"code": str(code.code), "count": len(ids)},
            now=self._clock.now(),
        )
        return ExportUserIdsResult(
            user_ids=[int(u) for u in ids],
            label=f"utm_{code.code}",
        )
