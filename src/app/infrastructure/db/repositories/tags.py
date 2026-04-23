"""TagRepository: упрощённая реализация для Этапа 2."""

from __future__ import annotations

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fanfics.ports import ITagRepository, TagRef
from app.domain.fanfics.value_objects import TagName, TagSlug
from app.domain.shared.types import FanficId, TagId
from app.infrastructure.db.models.fanfic_tag import FanficTag as FanficTagModel
from app.infrastructure.db.models.tag import Tag as TagModel


def _to_ref(m: TagModel) -> TagRef:
    return TagRef(
        id=TagId(m.id),
        name=TagName(m.name),
        slug=TagSlug(m.slug),
        kind=str(m.kind),
        approved=m.approved_at is not None,
    )


class TagRepository(ITagRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def ensure(self, *, name: TagName, slug: TagSlug, kind: str) -> tuple[TagRef, bool]:
        """INSERT ... ON CONFLICT (slug) DO UPDATE SET name=tags.name RETURNING *.

        UPDATE на то же значение — чтобы RETURNING гарантированно вернул строку.
        xmax=0 у строки означает «только что создано».
        """
        stmt = text(
            """
            INSERT INTO tags (name, slug, kind, usage_count, approved_at, created_at)
            VALUES (:name, :slug, CAST(:kind AS tag_kind), 0, NULL, NOW())
            ON CONFLICT (slug) DO UPDATE SET name = tags.name
            RETURNING id, name, slug, kind, approved_at, (xmax = 0) AS inserted
            """
        )
        result = await self._s.execute(stmt, {"name": str(name), "slug": str(slug), "kind": kind})
        row = result.one()
        ref = TagRef(
            id=TagId(row.id),
            name=TagName(row.name),
            slug=TagSlug(row.slug),
            kind=str(row.kind),
            approved=row.approved_at is not None,
        )
        created = bool(row.inserted)
        return ref, created

    async def list_by_fic(self, fic_id: FanficId) -> list[TagRef]:
        stmt = (
            select(TagModel)
            .join(FanficTagModel, FanficTagModel.tag_id == TagModel.id)
            .where(FanficTagModel.fic_id == int(fic_id))
            .order_by(TagModel.name.asc())
        )
        return [_to_ref(m) for m in (await self._s.execute(stmt)).scalars()]

    async def list_by_fic_ids(self, fic_ids: list[FanficId]) -> dict[FanficId, list[TagRef]]:
        if not fic_ids:
            return {}
        stmt = (
            select(FanficTagModel.fic_id, TagModel)
            .join(TagModel, TagModel.id == FanficTagModel.tag_id)
            .where(FanficTagModel.fic_id.in_([int(i) for i in fic_ids]))
            .order_by(TagModel.name.asc())
        )
        result: dict[FanficId, list[TagRef]] = {fid: [] for fid in fic_ids}
        for fid, m in (await self._s.execute(stmt)).all():
            result[FanficId(fid)].append(_to_ref(m))
        return result

    async def replace_for_fic(self, *, fic_id: FanficId, tag_ids: list[TagId]) -> None:
        await self._s.execute(delete(FanficTagModel).where(FanficTagModel.fic_id == int(fic_id)))
        for tid in dict.fromkeys(tag_ids):  # dedup сохраняя порядок
            self._s.add(FanficTagModel(fic_id=int(fic_id), tag_id=int(tid)))
        await self._s.flush()
