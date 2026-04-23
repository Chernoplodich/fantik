"""DTO для поиска: SearchCommand / SearchHit / SearchResult / SuggestCommand."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.domain.shared.types import FandomId, FanficId

SortMode = Literal["relevance", "newest", "updated", "top", "longest"]
SuggestKind = Literal["tag", "fandom", "character"]


@dataclass(frozen=True, kw_only=True)
class SearchCommand:
    """Поисковый запрос.

    `q` — свободный текст; может быть пустым (чистая навигация по фильтрам).
    Фильтры — списки идентификаторов/кодов. Пустые списки = без фильтра.
    """

    q: str = ""
    fandoms: list[int] = field(default_factory=list)
    age_ratings: list[str] = field(default_factory=list)  # коды (G/PG/R/...)
    tags: list[str] = field(default_factory=list)  # имена тегов (не slug)
    sort: SortMode = "relevance"
    limit: int = 10
    offset: int = 0


@dataclass(frozen=True, kw_only=True)
class SearchHit:
    fic_id: FanficId
    title: str
    author_nick: str | None
    fandom_id: FandomId
    fandom_name: str | None
    age_rating: str
    likes_count: int
    chapters_count: int
    cover_file_id: str | None = None
    """Telegram file_id обложки. Используется в инлайн-поиске для
    InlineQueryResultCachedPhoto. None → Article (без фото)."""


@dataclass(frozen=True, kw_only=True)
class SearchResult:
    hits: list[SearchHit]
    total: int
    facets: dict[str, dict[str, int]]
    degraded: bool = False
    """True — результаты пришли из fallback PG FTS (Meili недоступен).

    UI обязан показать баннер и отключить фильтры.
    """


@dataclass(frozen=True, kw_only=True)
class SuggestCommand:
    kind: SuggestKind
    prefix: str
    limit: int = 10
