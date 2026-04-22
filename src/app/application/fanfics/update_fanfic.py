"""Use case: правка meta фика (в статусах draft/rejected/revising)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.fanfics.ports import (
    IFanficRepository,
    IReferenceReader,
    ITagRepository,
)
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import ForbiddenActionError, TooManyTagsError
from app.domain.fanfics.services import entity_validator, tag_normalizer
from app.domain.fanfics.value_objects import (
    MAX_TAGS_PER_FIC,
    FanficTitle,
    Summary,
)
from app.domain.shared.types import FandomId, FanficId, TagId, UserId


@dataclass(frozen=True, kw_only=True)
class UpdateFanficCommand:
    fic_id: int
    author_id: int
    title: str
    summary: str
    summary_entities: list[dict[str, Any]]
    fandom_id: int
    age_rating_id: int
    tag_raws: list[str]
    cover_file_id: str | None = None
    cover_file_unique_id: str | None = None


class UpdateFanficUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        tags: ITagRepository,
        reference: IReferenceReader,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._tags = tags
        self._reference = reference
        self._clock = clock

    async def __call__(self, cmd: UpdateFanficCommand) -> None:
        title = FanficTitle(cmd.title)
        summary = Summary(cmd.summary)
        entities = entity_validator.validate(str(summary), cmd.summary_entities)

        raw_tags = [t for t in cmd.tag_raws if t and t.strip()]
        if len(raw_tags) > MAX_TAGS_PER_FIC:
            raise TooManyTagsError(f"Максимум {MAX_TAGS_PER_FIC} тегов на фик.")

        now = self._clock.now()

        async with self._uow:
            fic = await self._fanfics.get(FanficId(cmd.fic_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            if fic.author_id != UserId(cmd.author_id):
                raise ForbiddenActionError("Нельзя править чужой фик.")
            fandom = await self._reference.get_fandom(FandomId(cmd.fandom_id))
            if fandom is None:
                raise NotFoundError("Фандом не найден.")
            rating = await self._reference.get_age_rating(cmd.age_rating_id)
            if rating is None:
                raise NotFoundError("Возрастной рейтинг не найден.")

            fic.update_meta(
                title=title,
                summary=summary,
                summary_entities=entities,
                fandom_id=fandom.id,
                age_rating_id=rating.id,
                cover_file_id=cmd.cover_file_id,
                cover_file_unique_id=cmd.cover_file_unique_id,
                now=now,
            )
            await self._fanfics.save(fic)

            tag_ids: list[TagId] = []
            for raw in raw_tags:
                name, slug = tag_normalizer.normalize(raw)
                tag_ref, _created = await self._tags.ensure(
                    name=name, slug=slug, kind="freeform"
                )
                if tag_ref.id not in tag_ids:
                    tag_ids.append(tag_ref.id)
            await self._tags.replace_for_fic(fic_id=fic.id, tag_ids=tag_ids)

            self._uow.record_events(fic.pull_events())
            await self._uow.commit()
