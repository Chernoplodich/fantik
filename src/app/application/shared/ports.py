"""Общие порты application-слоя."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from app.domain.shared.events import DomainEvent


class UnitOfWork(Protocol):
    """Транзакционная граница.

    Use case:
        async with uow:
            ...
            uow.record_events(aggregate.pull_events())
            await uow.commit()
    """

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    def record_events(self, events: list[DomainEvent]) -> None: ...

    def collect_events(self) -> list[DomainEvent]: ...
