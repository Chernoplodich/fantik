"""Use cases админского CRUD фандомов."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.application.moderation.ports import IAuditLog
from app.application.reference.ports import FandomAdminRow, IFandomAdminRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domain.shared.slugify import slugify
from app.domain.shared.types import FandomId, UserId

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,126}[a-z0-9]$")

# 11 категорий, синхронно с разделами Книги фанфиков (ficbook).
# Старая `movies` оставлена в whitelist для обратной совместимости с тестами /
# историческими данными (миграция 0010 переводит существующие записи в `films`).
ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "anime",
        "books",
        "films",
        "series",
        "cartoons",
        "comics",
        "games",
        "musicals",
        "rpf",
        "originals",
        "other",
        "movies",  # legacy
    }
)
_ALLOWED_CATEGORIES = ALLOWED_CATEGORIES


@dataclass(frozen=True, kw_only=True)
class CreateFandomCommand:
    actor_id: int
    name: str
    category: str
    aliases: list[str]
    slug: str | None = None  # если None — сгенерируем из name


@dataclass(frozen=True, kw_only=True)
class UpdateFandomCommand:
    actor_id: int
    fandom_id: int
    name: str | None = None
    aliases: list[str] | None = None
    active: bool | None = None


def _validate_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValidationError("Slug: 3–128 символов [a-z0-9-], не начинается/не заканчивается '-'.")
    return slug


def _validate_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 256:
        raise ValidationError("Название фандома: 1–256 символов.")
    return name


def _validate_category(category: str) -> str:
    category = category.strip().lower()
    if category not in _ALLOWED_CATEGORIES:
        raise ValidationError(f"Категория: {sorted(_ALLOWED_CATEGORIES)}, получено {category!r}.")
    return category


def _normalize_aliases(aliases: list[str]) -> list[str]:
    clean = {a.strip() for a in aliases if a and a.strip()}
    return sorted(clean)


class CreateFandomUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: IFandomAdminRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: CreateFandomCommand) -> FandomAdminRow:
        name = _validate_name(cmd.name)
        category = _validate_category(cmd.category)
        aliases = _normalize_aliases(cmd.aliases)

        if cmd.slug:
            slug_base = _validate_slug(cmd.slug)
        else:
            slug_base = slugify(name)
            if not slug_base or len(slug_base) < 3:
                raise ValidationError(
                    "Не удалось сгенерировать slug из названия. "
                    "Дай более описательное название (минимум 3 латинских символа "
                    "или пару русских слов)."
                )

        # Ищем свободный slug: base, base-2, base-3, ... — на случай коллизий.
        async with self._uow:
            slug = slug_base
            suffix = 2
            while True:
                try:
                    row = await self._repo.create(
                        slug=slug, name=name, category=category, aliases=aliases
                    )
                    break
                except ConflictError:
                    if cmd.slug:
                        # Юзер явно задал slug — не подменяем, бросаем.
                        raise
                    slug = f"{slug_base}-{suffix}"
                    suffix += 1
                    if suffix > 50:
                        raise
            await self._audit.log(
                actor_id=UserId(int(cmd.actor_id)),
                action="fandom.create",
                target_type="fandom",
                target_id=int(row.id),
                payload={"slug": slug, "name": name, "category": category},
                now=self._clock.now(),
            )
            await self._uow.commit()
        return row


class UpdateFandomUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: IFandomAdminRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: UpdateFandomCommand) -> FandomAdminRow:
        fandom_id = FandomId(int(cmd.fandom_id))
        name = _validate_name(cmd.name) if cmd.name is not None else None
        aliases = _normalize_aliases(cmd.aliases) if cmd.aliases is not None else None
        async with self._uow:
            existing = await self._repo.get(fandom_id)
            if existing is None:
                raise NotFoundError("Фандом не найден.")
            row = await self._repo.update(
                fandom_id=fandom_id,
                name=name,
                aliases=aliases,
                active=cmd.active,
            )
            await self._audit.log(
                actor_id=UserId(int(cmd.actor_id)),
                action="fandom.update",
                target_type="fandom",
                target_id=int(row.id),
                payload={
                    "name": name,
                    "aliases": aliases,
                    "active": cmd.active,
                },
                now=self._clock.now(),
            )
            await self._uow.commit()
        return row


class ListFandomsAdminUseCase:
    def __init__(self, repo: IFandomAdminRepository) -> None:
        self._repo = repo

    async def __call__(self, *, active_only: bool = False) -> list[FandomAdminRow]:
        return await self._repo.list_all(active_only=active_only)


class ListFandomsByCategoryAdminUseCase:
    """Постраничный листинг фандомов в категории (включая inactive)."""

    def __init__(self, repo: IFandomAdminRepository) -> None:
        self._repo = repo

    async def __call__(
        self, *, category: str, limit: int = 10, offset: int = 0
    ) -> tuple[list[FandomAdminRow], int]:
        return await self._repo.list_by_category(category=category, limit=limit, offset=offset)


class SearchFandomsAdminUseCase:
    """Админский поиск фандомов по name+aliases (включая inactive)."""

    def __init__(self, repo: IFandomAdminRepository) -> None:
        self._repo = repo

    async def __call__(
        self,
        *,
        query: str,
        limit: int = 30,
        category: str | None = None,
    ) -> list[FandomAdminRow]:
        return await self._repo.search(query=query, limit=limit, category=category)


class CategoryStatsAdminUseCase:
    """Счётчики активных фандомов на категорию (для бейджей в picker)."""

    def __init__(self, repo: IFandomAdminRepository) -> None:
        self._repo = repo

    async def __call__(self) -> dict[str, int]:
        return await self._repo.count_by_category()
