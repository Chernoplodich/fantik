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
        moderator_id = UserId(cmd.moderator_id)
        async with self._uow:
            # Освободить собственные lock'и — если модератор нажал «Следующая»
            # не приняв решения по текущему case'у, он должен вернуться в очередь
            # (иначе был бы закрыт lock'ом на 15 мин и не попался бы повторно).
            await self._moderation.release_own_locks(moderator_id=moderator_id)

            case = await self._moderation.pick_next(moderator_id=moderator_id, now=now)
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

        return PickNextResult(card=ModerationCaseCard(case=case, fic_bundle=bundle, tags=tags))
