"""IndexFanficUseCase: собрать Meili-документ через ISearchDocSource и выполнить upsert/delete.

Идемпотентен: каждый вызов заново читает актуальное состояние фика. При пропаже фика
или смене статуса с APPROVED — документ удаляется из индекса (защита от race'ов между
archive и поздним enqueue из outbox).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.search.ports import (
    ISearchDocSource,
    ISearchIndex,
    SearchDocSource,
)
from app.core.logging import get_logger
from app.domain.shared.types import FanficId

log = get_logger(__name__)

_EXCERPT_CHAPTER_CHARS = 5_000
_EXCERPT_TOTAL = 20_000


def _build_excerpt(chapter_texts: list[str]) -> str:
    """Склеить первые несколько (обычно 3) глав — каждая до 5k — в общий excerpt до 20k."""
    pieces = [t[:_EXCERPT_CHAPTER_CHARS] for t in chapter_texts]
    excerpt = "\n\n".join(pieces)
    return excerpt[:_EXCERPT_TOTAL]


def to_meili_doc(src: SearchDocSource) -> dict[str, object]:
    return {
        "id": int(src.fic_id),
        "title": src.title,
        "summary": src.summary,
        "author_nick": src.author_nick,
        "fandom_id": int(src.fandom_id),
        "fandom_name": src.fandom_name,
        "fandom_aliases": list(src.fandom_aliases),
        "age_rating": src.age_rating,
        "age_rating_order": int(src.age_rating_order),
        "tags": list(src.tags),
        "characters": list(src.characters),
        "warnings": list(src.warnings),
        "chapters_count": int(src.chapters_count),
        "chars_count": int(src.chars_count),
        "likes_count": int(src.likes_count),
        "views_count": int(src.views_count),
        "reads_completed_count": int(src.reads_completed_count),
        "first_published_at": (
            int(src.first_published_at.timestamp()) if src.first_published_at else 0
        ),
        "updated_at": int(src.updated_at.timestamp()) if src.updated_at else 0,
        "chapters_text_excerpt": _build_excerpt(src.chapter_texts),
        # cover_file_id — Telegram file_id, не для поиска, только для UI:
        # не должен попадать в searchable attributes (это задача settings_bootstrap).
        "cover_file_id": src.cover_file_id or "",
    }


@dataclass(frozen=True, kw_only=True)
class IndexFanficCommand:
    fic_id: int


class IndexFanficUseCase:
    def __init__(self, source: ISearchDocSource, index: ISearchIndex) -> None:
        self._source = source
        self._index = index

    async def __call__(self, cmd: IndexFanficCommand) -> None:
        fid = FanficId(cmd.fic_id)
        src = await self._source.load(fid)

        if src is None:
            await self._index.delete(fid)
            log.info("index_fanfic_deleted", fic_id=int(fid))
            return

        doc = to_meili_doc(src)
        await self._index.upsert(doc)
        log.info("index_fanfic_upserted", fic_id=int(fid))
