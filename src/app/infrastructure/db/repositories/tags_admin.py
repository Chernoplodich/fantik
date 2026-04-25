"""PgTagAdminRepository + PgTagCandidatesReader — merge и поиск кандидатов."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reference.ports import (
    ITagAdminRepository,
    ITagCandidatesReader,
    TagCandidate,
)
from app.domain.shared.types import TagId
from app.infrastructure.db.models.tag import Tag as TagModel


class PgTagAdminRepository(ITagAdminRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def exists(self, tag_id: TagId) -> bool:
        stmt = select(TagModel.id).where(TagModel.id == int(tag_id))
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def merge(self, *, canonical_id: TagId, source_ids: list[TagId]) -> int:
        if not source_ids:
            return 0
        source_int = [int(s) for s in source_ids]

        # 1) Перепривязать fanfic_tags: sources → canonical.
        # ON CONFLICT DO NOTHING — если (fic_id, canonical) уже есть.
        reassign_stmt = text(
            """
            WITH updated AS (
                INSERT INTO fanfic_tags (fic_id, tag_id)
                SELECT DISTINCT fic_id, :canonical
                  FROM fanfic_tags
                 WHERE tag_id = ANY(:sources)
                ON CONFLICT (fic_id, tag_id) DO NOTHING
                RETURNING fic_id
            )
            SELECT count(*) FROM updated
            """
        )
        inserted = (
            await self._s.execute(
                reassign_stmt, {"canonical": int(canonical_id), "sources": source_int}
            )
        ).scalar_one()

        # Удалить исходные (fic_id, source_tag_id) пары.
        del_stmt = text("DELETE FROM fanfic_tags WHERE tag_id = ANY(:sources)")
        await self._s.execute(del_stmt, {"sources": source_int})

        # 2) Сложить usage_count в canonical, обнулить у sources.
        await self._s.execute(
            text(
                """
                UPDATE tags
                   SET usage_count = usage_count + COALESCE((
                     SELECT SUM(usage_count) FROM tags WHERE id = ANY(:sources)
                   ), 0)
                 WHERE id = :canonical
                """
            ),
            {"canonical": int(canonical_id), "sources": source_int},
        )
        await self._s.execute(
            text(
                "UPDATE tags SET usage_count = 0, merged_into_id = :canonical "
                "WHERE id = ANY(:sources)"
            ),
            {"canonical": int(canonical_id), "sources": source_int},
        )

        return int(inserted or 0)


class PgTagCandidatesReader(ITagCandidatesReader):
    """Ищет похожие теги: совпадение LOWER(name) — типичный случай дубля."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_candidates(self, *, limit: int = 50) -> list[TagCandidate]:
        stmt = text(
            """
            WITH grouped AS (
                SELECT LOWER(name) AS lname,
                       array_agg(id ORDER BY usage_count DESC, id) AS ids,
                       array_agg(name ORDER BY usage_count DESC, id) AS names
                  FROM tags
                 WHERE merged_into_id IS NULL
                 GROUP BY LOWER(name)
                HAVING count(*) > 1
                 LIMIT :lim
            )
            SELECT lname, ids, names FROM grouped
            """
        )
        rows = (await self._s.execute(stmt, {"lim": int(limit)})).all()
        out: list[TagCandidate] = []
        for r in rows:
            ids = list(r.ids)
            names = list(r.names)
            canonical_id = int(ids[0])
            canonical_name = str(names[0])
            for i in range(1, len(ids)):
                out.append(
                    TagCandidate(
                        canonical_id=TagId(canonical_id),
                        canonical_name=canonical_name,
                        source_id=TagId(int(ids[i])),
                        source_name=str(names[i]),
                    )
                )
        return out
