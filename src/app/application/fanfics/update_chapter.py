"""Use case: правка главы (только draft/rejected/revising)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import (
    ChapterCharsLimitExceededError,
    ForbiddenActionError,
)
from app.domain.fanfics.services import entity_validator
from app.domain.fanfics.value_objects import ChapterTitle
from app.domain.shared.types import ChapterId, UserId
from app.domain.shared.utf16 import utf16_length


@dataclass(frozen=True, kw_only=True)
class UpdateChapterCommand:
    chapter_id: int
    author_id: int
    title: str
    text: str
    entities: list[dict[str, Any]]


class UpdateChapterUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        clock: Clock,
        settings: Settings,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._chapters = chapters
        self._clock = clock
        self._settings = settings

    async def __call__(self, cmd: UpdateChapterCommand) -> None:
        title = ChapterTitle(cmd.title)
        text = cmd.text
        chars = utf16_length(text)
        if chars > self._settings.max_chapter_chars:
            raise ChapterCharsLimitExceededError(
                f"Глава длиннее {self._settings.max_chapter_chars} UTF-16 символов."
            )
        entities = entity_validator.validate(text, cmd.entities)

        now = self._clock.now()

        async with self._uow:
            chapter = await self._chapters.get(ChapterId(cmd.chapter_id))
            if chapter is None:
                raise NotFoundError("Глава не найдена.")
            fic = await self._fanfics.get(chapter.fic_id)
            if fic is None:
                raise NotFoundError("Фик не найден.")
            if fic.author_id != UserId(cmd.author_id):
                raise ForbiddenActionError("Нельзя править чужую главу.")

            old_chars = chapter.chars_count
            chapter.update_text(
                title=title,
                text=text,
                entities=entities,
                chars_count=chars,
                now=now,
            )
            await self._chapters.save(chapter)
            fic.replace_chars_delta(old=old_chars, new=chars)
            await self._fanfics.save(fic)

            self._uow.record_events(fic.pull_events() + chapter.pull_events())
            await self._uow.commit()
