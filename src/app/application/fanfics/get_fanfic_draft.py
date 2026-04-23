"""Use case: получить фик со всеми главами и тегами для карточки/правки."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import (
    FanficWithChapters,
    IFanficRepository,
    ITagRepository,
)
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import ForbiddenActionError
from app.domain.shared.types import FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class GetFanficDraftCommand:
    fic_id: int
    author_id: int


class GetFanficDraftUseCase:
    def __init__(
        self,
        fanfics: IFanficRepository,
        tags: ITagRepository,
    ) -> None:
        self._fanfics = fanfics
        self._tags = tags

    async def __call__(self, cmd: GetFanficDraftCommand) -> FanficWithChapters:
        bundle = await self._fanfics.get_with_chapters(FanficId(cmd.fic_id))
        if bundle is None:
            raise NotFoundError("Фик не найден.")
        if bundle.fic.author_id != UserId(cmd.author_id):
            raise ForbiddenActionError("Нельзя смотреть чужой черновик.")
        tags = await self._tags.list_by_fic(bundle.fic.id)
        return FanficWithChapters(fic=bundle.fic, chapters=bundle.chapters, tags=tags)
