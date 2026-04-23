"""PgSearchDocSource: читает плоский снимок фика из PG для индексации в Meili.

Использует одну сессию, читает fic + author + fandom + age_rating + tags + главы
несколькими подзапросами (без тяжёлых join'ов на все отношения сразу).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.search.ports import ISearchDocSource, SearchDocSource
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FanficId
from app.infrastructure.db.models.age_rating import AgeRating as AgeRatingModel
from app.infrastructure.db.models.chapter import Chapter as ChapterModel
from app.infrastructure.db.models.fandom import Fandom as FandomModel
from app.infrastructure.db.models.fanfic import Fanfic as FanficModel
from app.infrastructure.db.models.fanfic_tag import FanficTag as FanficTagModel
from app.infrastructure.db.models.tag import Tag as TagModel
from app.infrastructure.db.models.user import User as UserModel

_EXCERPT_CHAPTERS = 3


class PgSearchDocSource(ISearchDocSource):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def load(self, fic_id: FanficId | int) -> SearchDocSource | None:
        fid = int(fic_id)
        fic = await self._s.get(FanficModel, fid)
        if fic is None or fic.status != FicStatus.APPROVED:
            return None

        author = await self._s.get(UserModel, int(fic.author_id))
        fandom = await self._s.get(FandomModel, int(fic.fandom_id))
        rating = await self._s.get(AgeRatingModel, int(fic.age_rating_id))

        tag_rows = (
            await self._s.execute(
                select(TagModel.name, TagModel.kind)
                .join(FanficTagModel, FanficTagModel.tag_id == TagModel.id)
                .where(FanficTagModel.fic_id == fid)
            )
        ).all()

        tags: list[str] = []
        characters: list[str] = []
        warnings: list[str] = []
        for name, kind in tag_rows:
            if kind == "character":
                characters.append(str(name))
            elif kind == "warning":
                warnings.append(str(name))
            else:  # theme / freeform
                tags.append(str(name))

        ch_rows = (
            await self._s.execute(
                select(ChapterModel.text)
                .where(
                    ChapterModel.fic_id == fid,
                    ChapterModel.status == FicStatus.APPROVED,
                )
                .order_by(ChapterModel.number.asc())
                .limit(_EXCERPT_CHAPTERS)
            )
        ).all()
        chapter_texts: list[str] = [str(row[0]) for row in ch_rows]

        return SearchDocSource(
            fic_id=fid,
            title=str(fic.title),
            summary=str(fic.summary),
            author_nick=(author.author_nick if author and author.author_nick else "") or "",
            fandom_id=int(fic.fandom_id),
            fandom_name=str(fandom.name) if fandom else "",
            fandom_aliases=list(fandom.aliases) if fandom else [],
            age_rating=str(rating.code) if rating else "",
            age_rating_order=int(rating.sort_order) if rating else 0,
            tags=tags,
            characters=characters,
            warnings=warnings,
            chapters_count=int(fic.chapters_count),
            chars_count=int(fic.chars_count),
            likes_count=int(fic.likes_count),
            views_count=int(fic.views_count),
            reads_completed_count=int(fic.reads_completed_count),
            first_published_at=fic.first_published_at,
            updated_at=fic.updated_at,
            chapter_texts=chapter_texts,
            cover_file_id=str(fic.cover_file_id) if fic.cover_file_id else None,
        )
