"""PgSuggestReader: автодополнение тегов/фандомов/персонажей по префиксу (ILIKE)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.search.ports import ISuggestReader
from app.infrastructure.db.models.fandom import Fandom as FandomModel
from app.infrastructure.db.models.tag import Tag as TagModel

_VALID_TAG_KINDS = {"theme", "freeform", "character", "warning"}


class PgSuggestReader(ISuggestReader):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def by_prefix(self, *, kind: str, prefix: str, limit: int) -> list[str]:
        pattern = f"{prefix}%"

        if kind == "fandom":
            stmt = (
                select(FandomModel.name)
                .where(
                    FandomModel.active.is_(True),
                    FandomModel.name.ilike(pattern),
                )
                .limit(limit)
            )
            rows = (await self._s.execute(stmt)).scalars().all()
            return [str(r) for r in rows]

        tag_kind = kind if kind in _VALID_TAG_KINDS else "freeform"
        stmt = (
            select(TagModel.name)
            .where(
                TagModel.kind == tag_kind,
                TagModel.merged_into_id.is_(None),
                TagModel.name.ilike(pattern),
            )
            .order_by(TagModel.usage_count.desc())
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [str(r) for r in rows]
