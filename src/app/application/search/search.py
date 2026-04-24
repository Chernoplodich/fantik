"""SearchUseCase: primary (Meili) → fallback (PG FTS) при circuit-open или ошибке."""

from __future__ import annotations

from app.application.search.dto import SearchCommand, SearchResult
from app.application.search.ports import ISearchFallback, ISearchIndex
from app.core.logging import get_logger
from app.core.metrics import SEARCH_QUERIES

log = get_logger(__name__)


class SearchUseCase:
    def __init__(self, primary: ISearchIndex, fallback: ISearchFallback) -> None:
        self._primary = primary
        self._fallback = fallback

    async def __call__(self, cmd: SearchCommand) -> SearchResult:
        if self._primary.is_open():
            return await self._run_fallback(cmd)

        try:
            result = await self._primary.search(cmd)
            SEARCH_QUERIES.labels(backend="meili").inc()
            return result
        except Exception as e:
            log.warning("search_primary_failed", error=str(e))
            return await self._run_fallback(cmd)

    async def _run_fallback(self, cmd: SearchCommand) -> SearchResult:
        hits = await self._fallback.search(cmd.q, limit=cmd.limit, offset=cmd.offset)
        SEARCH_QUERIES.labels(backend="pg").inc()
        return SearchResult(
            hits=hits,
            total=len(hits),
            facets={},
            degraded=True,
        )
