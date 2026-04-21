"""Use case: создание UTM-кода админом."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.shared.ports import UnitOfWork
from app.application.tracking.ports import ITrackingRepository
from app.core.clock import Clock
from app.domain.shared.types import UserId
from app.domain.tracking.entities import TrackingCode
from app.domain.tracking.value_objects import TrackingCodeStr, generate_code


@dataclass(frozen=True, kw_only=True)
class CreateTrackingCodeCommand:
    created_by: int  # admin tg_id
    name: str
    description: str | None = None
    code: str | None = None  # если None — сгенерим


@dataclass(frozen=True, kw_only=True)
class CreateTrackingCodeResult:
    code: str
    id: int


class CreateTrackingCodeUseCase:
    def __init__(self, uow: UnitOfWork, tracking: ITrackingRepository, clock: Clock) -> None:
        self._uow = uow
        self._tracking = tracking
        self._clock = clock

    async def __call__(self, cmd: CreateTrackingCodeCommand) -> CreateTrackingCodeResult:
        if cmd.code:
            code_str = TrackingCodeStr(cmd.code)
        else:
            # генерируем, пока не найдём свободный
            for _ in range(5):
                candidate = generate_code()
                if await self._tracking.get_code_id(str(candidate)) is None:
                    code_str = candidate
                    break
            else:  # pragma: no cover — почти невероятно
                raise RuntimeError("Не удалось сгенерировать уникальный код")

        entity = TrackingCode(
            id=None,
            code=code_str,
            name=cmd.name,
            description=cmd.description,
            created_by=UserId(cmd.created_by),
            active=True,
            created_at=self._clock.now(),
        )
        async with self._uow:
            saved = await self._tracking.save_code(entity)
            await self._uow.commit()
        assert saved.id is not None
        return CreateTrackingCodeResult(code=str(saved.code), id=int(saved.id))
