"""TaskIQ: репагинация главы после approve/правки.

Запускается через `repaginate_chapter.kiq(chapter_id)`.
Идемпотентна (delete+insert + invalidate cache).
"""

from __future__ import annotations

from app.application.reading.paginate_chapter import (
    PaginateChapterCommand,
    PaginateChapterUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broker

log = get_logger(__name__)


@broker.task(task_name="repaginate_chapter")
async def repaginate_chapter(chapter_id: int) -> int:
    container = get_worker_container()
    async with container() as scope:
        uc = await scope.get(PaginateChapterUseCase)
        try:
            pages_count = await uc(PaginateChapterCommand(chapter_id=chapter_id))
        except DomainError:
            log.warning("repaginate_chapter_not_found", chapter_id=chapter_id)
            return 0
        log.info("repaginate_chapter_done", chapter_id=chapter_id, pages=pages_count)
        return pages_count
