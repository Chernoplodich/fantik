"""PgFandomAdminRepository — CRUD фандомов (admin only)."""

from __future__ import annotations

from sqlalchemy import func, select, text
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
        m = FandomModel(slug=slug, name=name, category=category, aliases=list(aliases), active=True)
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

    async def list_by_category(
        self, *, category: str, limit: int, offset: int
    ) -> tuple[list[FandomAdminRow], int]:
        cat = (category or "").strip().lower()
        total_stmt = select(func.count(FandomModel.id)).where(FandomModel.category == cat)
        main_stmt = (
            select(FandomModel)
            .where(FandomModel.category == cat)
            .order_by(FandomModel.name.asc())
            .limit(limit)
            .offset(offset)
        )
        total = int((await self._s.execute(total_stmt)).scalar_one())
        rows = (await self._s.execute(main_stmt)).scalars().all()
        return [_to_row(r) for r in rows], total

    async def search(
        self,
        *,
        query: str,
        limit: int = 30,
        category: str | None = None,
    ) -> list[FandomAdminRow]:
        """Поиск по name + aliases (ILIKE), включая inactive.

        Переиспользует SQL-паттерн из ReferenceReader.search_fandoms, но без
        фильтра active=True (админу нужно видеть всё).
        """
        q = (query or "").strip()
        if len(q) < 2:
            return []
        substr = f"%{q}%"
        prefix = f"{q}%"
        cat = category.strip().lower() if category else None

        sql_parts = [
            "SELECT id, slug, name, category, aliases, active",
            "FROM fandoms",
            "WHERE (",
            "  name ILIKE :substr",
            "  OR EXISTS (SELECT 1 FROM unnest(aliases) AS a WHERE a ILIKE :substr)",
            ")",
        ]
        if cat is not None:
            sql_parts.append("  AND category = :cat")
        sql_parts.append("ORDER BY")
        sql_parts.append("  CASE WHEN name ILIKE :prefix THEN 0 ELSE 1 END,")
        sql_parts.append("  active DESC,")
        sql_parts.append("  name ASC")
        sql_parts.append("LIMIT :limit")
        sql = text("\n".join(sql_parts))

        params: dict[str, object] = {"substr": substr, "prefix": prefix, "limit": limit}
        if cat is not None:
            params["cat"] = cat

        result = await self._s.execute(sql, params)
        return [
            FandomAdminRow(
                id=FandomId(int(row.id)),
                slug=str(row.slug),
                name=str(row.name),
                category=str(row.category),
                aliases=list(row.aliases or []),
                active=bool(row.active),
            )
            for row in result.mappings()
        ]

    async def count_by_category(self) -> dict[str, int]:
        """Счётчик активных фандомов на категорию.

        Возвращает {category_code: count} для всех категорий, в которых есть хотя бы
        один активный фандом. Категории без записей в выдачу не попадают —
        у вызывающей стороны (UI) есть дефолт 0.
        """
        stmt = (
            select(FandomModel.category, func.count(FandomModel.id))
            .where(FandomModel.active.is_(True))
            .group_by(FandomModel.category)
        )
        rows = (await self._s.execute(stmt)).all()
        return {str(cat): int(cnt) for cat, cnt in rows}
