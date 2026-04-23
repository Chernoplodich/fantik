"""PgFtsSearch: PostgreSQL FTS-fallback для случая недоступности Meili.

- Использует существующий STORED tsvector `chapters.tsv_text`.
- Пустой q → топ-N по `likes_count DESC` (иначе инлайн-бот без запроса был бы пустым).
- Фильтры НЕ применяются (только базовый q-поиск + сортировка по rank).
- На границе `application/` порт отдаёт `degraded=True` — UI отключает фильтры.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.search.dto import SearchHit
from app.application.search.ports import ISearchFallback
from app.domain.shared.types import FandomId, FanficId

_SQL_Q = """
SELECT DISTINCT ON (f.id)
       f.id,
       f.title,
       u.author_nick,
       f.fandom_id,
       fd.name AS fandom_name,
       ar.code AS age_rating,
       f.likes_count,
       f.chapters_count,
       f.cover_file_id,
       ts_rank(ch.tsv_text, plainto_tsquery('russian', :q))
         + ts_rank(
             to_tsvector('russian', f.title || ' ' || f.summary),
             plainto_tsquery('russian', :q)
         ) AS rank
  FROM fanfics f
  JOIN users u       ON u.id = f.author_id
  JOIN fandoms fd    ON fd.id = f.fandom_id
  JOIN age_ratings ar ON ar.id = f.age_rating_id
  LEFT JOIN chapters ch ON ch.fic_id = f.id
                       AND ch.status = 'approved'
 WHERE f.status = 'approved'
   AND (
        ch.tsv_text @@ plainto_tsquery('russian', :q)
     OR to_tsvector('russian', f.title || ' ' || f.summary)
        @@ plainto_tsquery('russian', :q)
   )
 ORDER BY f.id, rank DESC
 LIMIT :lim OFFSET :off
"""

_SQL_TOP = """
SELECT f.id,
       f.title,
       u.author_nick,
       f.fandom_id,
       fd.name AS fandom_name,
       ar.code AS age_rating,
       f.likes_count,
       f.chapters_count,
       f.cover_file_id
  FROM fanfics f
  JOIN users u        ON u.id = f.author_id
  JOIN fandoms fd     ON fd.id = f.fandom_id
  JOIN age_ratings ar ON ar.id = f.age_rating_id
 WHERE f.status = 'approved'
 ORDER BY f.likes_count DESC, f.first_published_at DESC NULLS LAST, f.id DESC
 LIMIT :lim OFFSET :off
"""


class PgFtsSearch(ISearchFallback):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def search(self, q: str, *, limit: int, offset: int) -> list[SearchHit]:
        q_stripped = q.strip()
        if not q_stripped:
            # Пустой запрос → «Топ» по лайкам. Важно для инлайн-режима:
            # пользователь открывает `@bot ` без текста и видит популярное.
            rows = (
                await self._s.execute(text(_SQL_TOP), {"lim": int(limit), "off": int(offset)})
            ).all()
        else:
            rows = (
                await self._s.execute(
                    text(_SQL_Q),
                    {"q": q_stripped, "lim": int(limit), "off": int(offset)},
                )
            ).all()

        hits: list[SearchHit] = []
        for row in rows:
            hits.append(
                SearchHit(
                    fic_id=FanficId(int(row.id)),
                    title=str(row.title or ""),
                    author_nick=(str(row.author_nick) if row.author_nick else None),
                    fandom_id=FandomId(int(row.fandom_id)),
                    fandom_name=(str(row.fandom_name) if row.fandom_name else None),
                    age_rating=str(row.age_rating or ""),
                    likes_count=int(row.likes_count or 0),
                    chapters_count=int(row.chapters_count or 0),
                    cover_file_id=(str(row.cover_file_id) if row.cover_file_id else None),
                )
            )
        return hits
