"""Порты админских CRUD по справочникам (фандомы, теги, заявки на фандом)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.reference.entities import FandomProposal
from app.domain.reference.value_objects import ProposalId
from app.domain.shared.types import FandomId, TagId, UserId


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

    async def list_by_category(
        self, *, category: str, limit: int, offset: int
    ) -> tuple[list[FandomAdminRow], int]:
        """Все фандомы категории (включая inactive). Сортировка по name asc.

        Возвращает (page, total) для пагинации.
        """
        ...

    async def search(
        self,
        *,
        query: str,
        limit: int = 30,
        category: str | None = None,
    ) -> list[FandomAdminRow]:
        """Поиск по name + aliases (ILIKE), включая inactive.

        Минимальная длина запроса — 2 символа. Сортировка: prefix-match → name asc.
        Если задана `category`, ограничивает выборку категорией.
        """
        ...

    async def count_by_category(self) -> dict[str, int]:
        """Счётчик активных фандомов на категорию (для бейджей в picker)."""
        ...


class ITagAdminRepository(Protocol):
    async def merge(self, *, canonical_id: TagId, source_ids: list[TagId]) -> int:
        """Выполнить merge: перепривязать fanfic_tags, пометить sources как merged.

        Возвращает число строк в fanfic_tags, чей tag_id был изменён.
        """
        ...

    async def exists(self, tag_id: TagId) -> bool: ...


class ITagCandidatesReader(Protocol):
    async def list_candidates(self, *, limit: int = 50) -> list[TagCandidate]:
        """Найти похожие теги: одинаковый LOWER(name) или latinise/homoglyph-маппинг."""
        ...


# ---------- fandom proposals ----------


@dataclass(frozen=True, kw_only=True)
class FandomProposalRow:
    """DTO для админ-UI: список заявок и карточка."""

    id: ProposalId
    name: str
    category_hint: str
    comment: str | None
    requested_by: UserId
    status: str  # 'pending' | 'approved' | 'rejected'
    reviewed_by: UserId | None
    reviewed_at: datetime | None
    decision_comment: str | None
    created_fandom_id: FandomId | None
    created_at: datetime


class IFandomProposalRepository(Protocol):
    async def create(
        self,
        *,
        requested_by: UserId,
        name: str,
        category_hint: str,
        comment: str | None,
        now: datetime,
    ) -> FandomProposal:
        """Создать pending-заявку. Бросает ConflictError при дублировании
        (анти-дубль uq_fandom_proposals_open_per_user_name).
        """
        ...

    async def get(self, proposal_id: ProposalId) -> FandomProposal | None: ...

    async def save(self, proposal: FandomProposal) -> None:
        """Сохранить изменённое (после approve/reject) состояние."""
        ...

    async def list_pending(self, *, limit: int = 50) -> list[FandomProposalRow]: ...

    async def list_recent(
        self, *, status: str | None = None, limit: int = 50
    ) -> list[FandomProposalRow]: ...


class IFandomProposalNotifier(Protocol):
    async def notify_submitted(self, *, requested_by: UserId, name: str) -> None: ...

    async def notify_approved(
        self,
        *,
        requested_by: UserId,
        name: str,
        fandom_id: FandomId,
    ) -> None: ...

    async def notify_rejected(
        self,
        *,
        requested_by: UserId,
        name: str,
        reason: str | None,
    ) -> None: ...
