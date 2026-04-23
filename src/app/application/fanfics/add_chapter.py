"""Use case: добавить главу к существующему фику."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.domain.fanfics.entities import Chapter
from app.domain.fanfics.exceptions import (
    ChapterCharsLimitExceededError,
    FanficChapterLimitExceededError,
    ForbiddenActionError,
    WrongStatusError,
)
from app.domain.fanfics.services import entity_validator
from app.domain.fanfics.value_objects import (
    ChapterNumber,
    ChapterTitle,
    FicStatus,
)
from app.domain.shared.types import ChapterId, FanficId, UserId
from app.domain.shared.utf16 import utf16_length

_APPENDABLE_STATUSES: frozenset[FicStatus] = frozenset(
    {FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING, FicStatus.APPROVED}
)


@dataclass(frozen=True, kw_only=True)
class AddChapterCommand:
    fic_id: int
    author_id: int
    title: str
    text: str
    entities: list[dict[str, Any]]


@dataclass(frozen=True, kw_only=True)
class AddChapterResult:
    chapter_id: int
    number: int


class AddChapterUseCase:
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

    async def __call__(self, cmd: AddChapterCommand) -> AddChapterResult:
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
            fic = await self._fanfics.get(FanficId(cmd.fic_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            if fic.author_id != UserId(cmd.author_id):
                raise ForbiddenActionError("Нельзя добавить главу в чужой фик.")
            if fic.status not in _APPENDABLE_STATUSES:
                raise WrongStatusError(
                    "Добавить главу можно только в draft/rejected/revising/approved."
                )
            count = await self._chapters.count_by_fic(fic.id)
            if count >= self._settings.max_chapters_per_fic:
                raise FanficChapterLimitExceededError(
                    f"Максимум {self._settings.max_chapters_per_fic} глав на фик."
                )
            number = ChapterNumber(await self._chapters.next_number(fic.id))

            chapter = Chapter.create_draft(
                fic_id=fic.id,
                number=number,
                title=title,
                text=text,
                entities=entities,
                chars_count=chars,
                now=now,
            )
            chapter = await self._chapters.save(chapter)
            fic.bump_chapters(chars_delta=chars)
            fic.announce_chapter_added(chapter_id=ChapterId(int(chapter.id)), number=int(number))
            await self._fanfics.save(fic)

            events = fic.pull_events() + chapter.pull_events()
            self._uow.record_events(events)
            await self._uow.commit()

        return AddChapterResult(chapter_id=int(chapter.id), number=int(number))
