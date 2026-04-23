"""PgFandomAdminRepository — CRUD фандомов (admin only)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reference.ports import FandomAdminRow, IFandomAdminRepository
from app.core.errors import ConflictError, NotFoundError
from app.domain.shared.types import FandomId
from app.infrastructure.db.models.fandom import Fandom as FandomModel


def _to_row(m: FandomModel) -> FandomAdminRow:
    return FandomAdminRow(
        id=FandomId(int(m.id)),
        slug=str(m.slug),
        name=str(m.name),
        category=str(m.category),
        aliases=list(m.aliases or []),
        active=bool(m.active),
    )


class PgFandomAdminRepository(IFandomAdminRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_all(self, *, active_only: bool = False) -> list[FandomAdminRow]:
        stmt = select(FandomModel).order_by(FandomModel.category, FandomModel.name)
        if active_only:
            stmt = stmt.where(FandomModel.active.is_(True))
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_row(r) for r in rows]

    async def get(self, fandom_id: FandomId) -> FandomAdminRow | None:
        m = await self._s.get(FandomModel, int(fandom_id))
        return _to_row(m) if m else None

    async def create(
        self,
        *,
        slug: str,
        name: str,
        category: str,
        aliases: list[str],
    ) -> FandomAdminRow:
        existing = (
            await self._s.execute(select(FandomModel).where(FandomModel.slug == slug))
        ).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Фандом со slug «{slug}» уже существует.")
        m = FandomModel(
            slug=slug, name=name, category=category, aliases=list(aliases), active=True
        )
        self._s.add(m)
        await self._s.flush()
        return _to_row(m)

    async def update(
        self,
        *,
        fandom_id: FandomId,
        name: str | None = None,
        aliases: list[str] | None = None,
        active: bool | None = None,
    ) -> FandomAdminRow:
        m = await self._s.get(FandomModel, int(fandom_id))
        if m is None:
            raise NotFoundError(f"Фандом #{int(fandom_id)} не найден.")
        if name is not None:
            m.name = name
        if aliases is not None:
            m.aliases = list(aliases)
        if active is not None:
            m.active = bool(active)
        await self._s.flush()
        return _to_row(m)
