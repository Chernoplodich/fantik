"""MeiliSearchIndex: адаптер Meilisearch для ISearchIndex с circuit-breaker.

- 3 подряд ошибки на search/upsert/delete → контур открывается на 60 ± 10 секунд
  (jitter, чтобы в multi-process окружении пробы не синхронизировались).
- Успешный вызов сбрасывает счётчик.
- `is_open()` используется SearchUseCase для решения «идти в fallback?».
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from meilisearch_python_sdk import AsyncClient
from meilisearch_python_sdk.models.search import SearchResults

from app.application.search.dto import SearchCommand, SearchHit, SearchResult
from app.application.search.filter_builder import build_facets, build_filter, build_sort
from app.application.search.ports import ISearchIndex
from app.core.logging import get_logger
from app.domain.shared.types import FandomId, FanficId
from app.infrastructure.search.client import INDEX_NAME, PRIMARY_KEY

log = get_logger(__name__)

_FAIL_THRESHOLD = 3
_OPEN_SECONDS = 60.0
_JITTER_SECONDS = 10.0


class MeiliSearchIndex(ISearchIndex):
    def __init__(self, client: AsyncClient) -> None:
        self._client = client
        self._consecutive_fails = 0
        self._open_until: datetime | None = None

    # ---------- circuit breaker ----------

    def is_open(self) -> bool:
        if self._open_until is None:
            return False
        if datetime.now(tz=UTC) >= self._open_until:
            # таймер истёк — half-open: пробуем следующий запрос
            self._open_until = None
            self._consecutive_fails = 0
            return False
        return True

    def _record_success(self) -> None:
        self._consecutive_fails = 0
        self._open_until = None

    def _record_failure(self, op: str, error: Exception) -> None:
        self._consecutive_fails += 1
        log.warning("meili_op_failed", op=op, error=str(error), fails=self._consecutive_fails)
        if self._consecutive_fails >= _FAIL_THRESHOLD:
            jitter = random.uniform(-_JITTER_SECONDS, _JITTER_SECONDS)
            self._open_until = datetime.now(tz=UTC) + timedelta(seconds=_OPEN_SECONDS + jitter)
            log.warning(
                "meili_circuit_opened",
                until=self._open_until.isoformat(),
                fails=self._consecutive_fails,
            )

    # ---------- operations ----------

    async def search(self, cmd: SearchCommand) -> SearchResult:
        index = self._client.index(INDEX_NAME)
        filt = build_filter(cmd)
        sort = build_sort(cmd)
        facets = build_facets()
        try:
            resp: SearchResults = await index.search(
                query=cmd.q or None,
                offset=cmd.offset,
                limit=cmd.limit,
                filter=filt if filt else None,
                facets=facets,
                sort=sort,
            )
        except Exception as e:
            self._record_failure("search", e)
            raise
        self._record_success()

        hits: list[SearchHit] = []
        for raw in resp.hits:
            hits.append(_hit_from_raw(raw))
        facet_dist = dict(resp.facet_distribution or {}) if resp.facet_distribution else {}

        # SDK даёт total_hits (если exhaustive) либо estimated_total_hits.
        total = int(getattr(resp, "total_hits", None) or getattr(resp, "estimated_total_hits", 0))

        return SearchResult(hits=hits, total=total, facets=facet_dist, degraded=False)

    async def upsert(self, doc: dict[str, object]) -> None:
        index = self._client.index(INDEX_NAME)
        try:
            await index.add_documents([doc], primary_key=PRIMARY_KEY)
        except Exception as e:
            self._record_failure("upsert", e)
            raise
        self._record_success()

    async def delete(self, fic_id: FanficId | int) -> None:
        index = self._client.index(INDEX_NAME)
        try:
            await index.delete_document(str(int(fic_id)))
        except Exception as e:
            self._record_failure("delete", e)
            raise
        self._record_success()

    async def bulk_upsert(self, docs: list[dict[str, object]]) -> None:
        if not docs:
            return
        index = self._client.index(INDEX_NAME)
        try:
            await index.add_documents_in_batches(docs, batch_size=1000, primary_key=PRIMARY_KEY)
        except Exception as e:
            self._record_failure("bulk_upsert", e)
            raise
        self._record_success()


def _hit_from_raw(raw: dict[str, object]) -> SearchHit:
    cover_raw = raw.get("cover_file_id")
    return SearchHit(
        fic_id=FanficId(int(raw.get("id", 0))),
        title=str(raw.get("title") or ""),
        author_nick=(str(raw["author_nick"]) if raw.get("author_nick") else None),
        fandom_id=FandomId(int(raw.get("fandom_id", 0))),
        fandom_name=(str(raw["fandom_name"]) if raw.get("fandom_name") else None),
        age_rating=str(raw.get("age_rating") or ""),
        likes_count=int(raw.get("likes_count", 0) or 0),
        chapters_count=int(raw.get("chapters_count", 0) or 0),
        cover_file_id=(str(cover_raw) if cover_raw else None),
    )
