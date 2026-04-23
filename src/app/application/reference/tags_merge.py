"""Use case: merge тегов.

В одной транзакции:
  - перепривязывает fanfic_tags.tag_id: sources → canonical;
  - помечает sources.merged_into_id = canonical;
  - пересчитывает usage_count у canonical и зануляет у sources;
  - audit-log.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.moderation.ports import IAuditLog
from app.application.reference.ports import (
    ITagAdminRepository,
    ITagCandidatesReader,
    TagCandidate,
)
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError, ValidationError
from app.domain.shared.types import TagId, UserId


@dataclass(frozen=True, kw_only=True)
class MergeTagsCommand:
    actor_id: int
    canonical_id: int
    source_ids: list[int]


@dataclass(frozen=True, kw_only=True)
class MergeTagsResult:
    rows_reassigned: int


class MergeTagsUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ITagAdminRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: MergeTagsCommand) -> MergeTagsResult:
        if not cmd.source_ids:
            raise ValidationError("Нужен хотя бы один source-тег для merge.")
        if cmd.canonical_id in cmd.source_ids:
            raise ValidationError("canonical_id не может быть в source_ids.")

        canonical = TagId(int(cmd.canonical_id))
        sources = [TagId(int(s)) for s in cmd.source_ids]

        async with self._uow:
            if not await self._repo.exists(canonical):
                raise NotFoundError(f"Canonical-тег #{canonical} не найден.")
            for s in sources:
                if not await self._repo.exists(s):
                    raise NotFoundError(f"Source-тег #{s} не найден.")

            rows = await self._repo.merge(
                canonical_id=canonical, source_ids=sources
            )
            await self._audit.log(
                actor_id=UserId(int(cmd.actor_id)),
                action="tag.merge",
                target_type="tag",
                target_id=int(canonical),
                payload={
                    "canonical_id": int(canonical),
                    "source_ids": [int(s) for s in sources],
                    "rows_reassigned": int(rows),
                },
                now=self._clock.now(),
            )
            await self._uow.commit()

        return MergeTagsResult(rows_reassigned=rows)


class ListMergeCandidatesUseCase:
    def __init__(self, reader: ITagCandidatesReader) -> None:
        self._reader = reader

    async def __call__(self, *, limit: int = 50) -> list[TagCandidate]:
        return await self._reader.list_candidates(limit=limit)
