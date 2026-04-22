"""Use case: удалить главу-черновик."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.shared.ports import UnitOfWork
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import ForbiddenActionError, WrongStatusError
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, UserId


@dataclass(frozen=True, kw_only=True)
class DeleteDraftChapterCommand:
    chapter_id: int
    author_id: int


class DeleteDraftChapterUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._chapters = chapters

    async def __call__(self, cmd: DeleteDraftChapterCommand) -> None:
        async with self._uow:
            chapter = await self._chapters.get(ChapterId(cmd.chapter_id))
            if chapter is None:
                raise NotFoundError("Глава не найдена.")
            fic = await self._fanfics.get(chapter.fic_id)
            if fic is None:
                raise NotFoundError("Фик не найден.")
            if fic.author_id != UserId(cmd.author_id):
                raise ForbiddenActionError("Нельзя удалять чужую главу.")
            if chapter.status != FicStatus.DRAFT:
                raise WrongStatusError("Удалять можно только draft-главы.")

            chars = chapter.chars_count
            await self._chapters.delete(chapter.id)
            fic.drop_chapter(chars_delta=chars)
            await self._fanfics.save(fic)

            await self._uow.commit()
