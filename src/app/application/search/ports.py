"""Порты application-слоя поиска. Только Protocol, без реализаций."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.application.search.dto import SearchCommand, SearchHit, SearchResult
from app.domain.shared.types import FanficId


@dataclass(frozen=True, kw_only=True)
class SearchDocSource:
    """Плоский снимок всех данных, нужных для индексации фика в Meili.

    Читается одним запросом из PG (с join'ами), чтобы IndexFanficUseCase не знал,
    про сколько репозиториев нужно пройти.
    """

    fic_id: int
    title: str
    summary: str
    author_nick: str
    fandom_id: int
    fandom_name: str
    fandom_aliases: list[str] = field(default_factory=list)
    fandom_category: str = ""
    """Код категории фандома (anime/books/films/...). Индексируется как
    filterable attribute (см. settings_bootstrap)."""
    age_rating: str
    age_rating_order: int
    tags: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    chapters_count: int
    chars_count: int
    likes_count: int
    views_count: int
    reads_completed_count: int
    first_published_at: datetime | None
    updated_at: datetime | None
    chapter_texts: list[str] = field(default_factory=list)
    """Тексты первых N approved-глав (N обычно = 3), в порядке возрастания number."""
    cover_file_id: str | None = None
    """Telegram file_id обложки — индексируется в Meili для инлайн-фото-результата."""


class ISearchDocSource(Protocol):
    """Источник плоского снимка фика для индексации."""

    async def load(self, fic_id: FanficId | int) -> SearchDocSource | None:
        """Вернёт None, если фик не существует ИЛИ не в статусе APPROVED."""
        ...


class ISearchIndex(Protocol):
    """Primary backend (Meilisearch). Держит circuit-breaker state."""

    async def search(self, cmd: SearchCommand) -> SearchResult: ...

    async def upsert(self, doc: dict[str, object]) -> None: ...

    async def delete(self, fic_id: FanficId | int) -> None: ...

    async def bulk_upsert(self, docs: list[dict[str, object]]) -> None: ...

    def is_open(self) -> bool:
        """True — контур разомкнут (Meili недоступен); SearchUseCase должен идти в fallback."""
        ...


class ISearchFallback(Protocol):
    """PG FTS fallback. Фильтры игнорируются (только базовый q-поиск + сортировка по rank)."""

    async def search(self, q: str, *, limit: int, offset: int) -> list[SearchHit]: ...


class ISearchCache(Protocol):
    """msgpack-кэш: универсальный TTL-кэш для произвольных JSON-совместимых значений.

    Используется инлайн-режимом (`list[dict]` — карточки) и suggest'ом (`list[str]`).
    """

    async def get(self, key: str) -> object | None: ...

    async def setex(self, key: str, ttl_s: int, value: object) -> None: ...


class ISearchIndexQueue(Protocol):
    """Адаптер TaskIQ-очереди индексации.

    `enqueue_debounced` — ЕДИНСТВЕННЫЙ случай прямого вызова из use case
    (используется в ToggleLikeUseCase, чтобы агрегировать лайки за 60с).

    Для approve/edit/archive события идут через outbox →
    `outbox_dispatcher` → `enqueue`, что гарантирует after-commit.
    """

    async def enqueue(self, fic_id: FanficId | int) -> None: ...

    async def enqueue_debounced(self, fic_id: FanficId | int, ttl_s: int = 60) -> None: ...


class ISuggestReader(Protocol):
    """Автодополнение тегов/фандомов/персонажей по префиксу."""

    async def by_prefix(self, *, kind: str, prefix: str, limit: int) -> list[str]: ...
