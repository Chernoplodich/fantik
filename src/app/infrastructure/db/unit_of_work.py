"""UoW для SQLAlchemy + буфер доменных событий."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.shared.ports import UnitOfWork as UnitOfWorkPort
from app.domain.shared.events import DomainEvent

UnitOfWork = UnitOfWorkPort  # re-export для удобства импорта из инфры


class SqlAlchemyUnitOfWork:
    """Реализация UnitOfWork поверх AsyncSession.

    - `async with uow:` открывает транзакцию (`begin()`).
    - `commit()` коммитит и очищает буфер событий.
    - `rollback()` откатывает.
    - Собранные через `record_events` события остаются после commit для последующей публикации
      (например, в outbox-диспетчер).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._events: list[DomainEvent] = []
        self._in_tx: bool = False

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def __aenter__(self) -> Self:
        if self._session.in_transaction():
            self._in_tx = True
            return self
        await self._session.begin()
        self._in_tx = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None and self._session.in_transaction():
            await self._session.rollback()
        # если сценарий корректно отработал, но не сделал commit — откатимся
        elif self._session.in_transaction():
            await self._session.rollback()
        self._in_tx = False

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    def record_events(self, events: list[DomainEvent]) -> None:
        self._events.extend(events)

    def collect_events(self) -> list[DomainEvent]:
        out, self._events = self._events, []
        return out
