"""Порты админских CRUD по справочникам (фандомы, теги)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.shared.types import FandomId, TagId


@dataclass(frozen=True, kw_only=True)
class FandomAdminRow:
    id: FandomId
    slug: str
    name: str
    category: str
    aliases: list[str]
    active: bool


@dataclass(frozen=True, kw_only=True)
class TagCandidate:
    """Две tag-строки, похожие друг на друга — кандидат в merge."""

    canonical_id: TagId
    canonical_name: str
    source_id: TagId
    source_name: str


class IFandomAdminRepository(Protocol):
    async def list_all(self, *, active_only: bool = False) -> list[FandomAdminRow]: ...

    async def get(self, fandom_id: FandomId) -> FandomAdminRow | None: ...

    async def create(
        self,
        *,
        slug: str,
        name: str,
        category: str,
        aliases: list[str],
    ) -> FandomAdminRow: ...

    async def update(
        self,
        *,
        fandom_id: FandomId,
        name: str | None = None,
        aliases: list[str] | None = None,
        active: bool | None = None,
    ) -> FandomAdminRow: ...


class ITagAdminRepository(Protocol):
    async def merge(
        self, *, canonical_id: TagId, source_ids: list[TagId]
    ) -> int:
        """Выполнить merge: перепривязать fanfic_tags, пометить sources как merged.

        Возвращает число строк в fanfic_tags, чей tag_id был изменён.
        """
        ...

    async def exists(self, tag_id: TagId) -> bool: ...


class ITagCandidatesReader(Protocol):
    async def list_candidates(self, *, limit: int = 50) -> list[TagCandidate]:
        """Найти похожие теги: одинаковый LOWER(name) или latinise/homoglyph-маппинг."""
        ...
