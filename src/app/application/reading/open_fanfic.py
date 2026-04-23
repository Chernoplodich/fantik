"""Use case: открыть карточку фика — cover + заголовок + кнопки чтения."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.reading.ports import IReadingProgressRepository
from app.core.errors import NotFoundError
from app.domain.fanfics.entities import Fanfic
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class OpenFanficCommand:
    user_id: int
    fic_id: int


@dataclass(frozen=True, kw_only=True)
class OpenFanficResult:
    fic: Fanfic
    total_chapters: int
    has_progress: bool
    progress_chapter_id: int | None
    progress_chapter_number: int | None
    progress_page_no: int | None


class OpenFanficUseCase:
    def __init__(
        self,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        progress: IReadingProgressRepository,
    ) -> None:
        self._fanfics = fanfics
        self._chapters = chapters
        self._progress = progress

    async def __call__(self, cmd: OpenFanficCommand) -> OpenFanficResult:
        fic_id = FanficId(cmd.fic_id)
        user_id = UserId(cmd.user_id)
        fic = await self._fanfics.get(fic_id)
        if fic is None:
            raise NotFoundError("Фик недоступен.")

        # Автор может видеть свой фик в любом статусе кроме ARCHIVED,
        # остальные — только APPROVED.
        viewer_is_author = fic.author_id == user_id
        if viewer_is_author:
            if fic.status == FicStatus.ARCHIVED:
                raise NotFoundError("Фик архивирован.")
        elif fic.status != FicStatus.APPROVED:
            raise NotFoundError("Фик недоступен.")

        # Автору показываем главы в статусах draft/pending/approved/rejected/revising.
        # Читателю — только approved.
        if viewer_is_author:
            author_visible = {
                FicStatus.DRAFT,
                FicStatus.PENDING,
                FicStatus.APPROVED,
                FicStatus.REJECTED,
                FicStatus.REVISING,
            }
            visible_chapters = [
                c for c in await self._chapters.list_by_fic(fic_id) if c.status in author_visible
            ]
        else:
            visible_chapters = [
                c
                for c in await self._chapters.list_by_fic(fic_id)
                if c.status == FicStatus.APPROVED
            ]
        visible_chapters.sort(key=lambda c: int(c.number))

        prog = await self._progress.get(UserId(cmd.user_id), fic_id)
        chapter_number: int | None = None
        if prog is not None:
            for c in visible_chapters:
                if int(c.id) == int(prog.chapter_id):
                    chapter_number = int(c.number)
                    break

        return OpenFanficResult(
            fic=fic,
            total_chapters=len(visible_chapters),
            has_progress=prog is not None and chapter_number is not None,
            progress_chapter_id=int(prog.chapter_id) if prog else None,
            progress_chapter_number=chapter_number,
            progress_page_no=int(prog.page_no) if prog else None,
        )
