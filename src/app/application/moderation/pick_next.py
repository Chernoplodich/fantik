"""Use case: модератор забирает следующее задание (FOR UPDATE SKIP LOCKED)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import (
    FanficWithChapters,
    IFanficRepository,
    ITagRepository,
    TagRef,
)
from app.application.moderation.ports import IModerationRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.domain.moderation.entities import ModerationCase
from app.domain.shared.types import UserId


@dataclass(frozen=True, kw_only=True)
class PickNextCommand:
    moderator_id: int


@dataclass(frozen=True, kw_only=True)
class ModerationCaseCard:
    case: ModerationCase
    fic_bundle: FanficWithChapters
    tags: list[TagRef]


@dataclass(frozen=True, kw_only=True)
class PickNextResult:
    card: ModerationCaseCard | None


class PickNextUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        fanfics: IFanficRepository,
        tags: ITagRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._moderation = moderation
        self._fanfics = fanfics
        self._tags = tags
        self._clock = clock

    async def __call__(self, cmd: PickNextCommand) -> PickNextResult:
        now = self._clock.now()
        async with self._uow:
            case = await self._moderation.pick_next(
                moderator_id=UserId(cmd.moderator_id), now=now
            )
            if case is None:
                await self._uow.commit()
                return PickNextResult(card=None)

            bundle = await self._fanfics.get_with_chapters(case.fic_id)
            if bundle is None:
                await self._uow.commit()
                return PickNextResult(card=None)
            tags = await self._tags.list_by_fic(case.fic_id)

            self._uow.record_events(case.pull_events())
            await self._uow.commit()

        return PickNextResult(
            card=ModerationCaseCard(case=case, fic_bundle=bundle, tags=tags)
        )
