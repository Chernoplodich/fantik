"""Адаптер IRepaginationQueue → TaskIQ."""

from __future__ import annotations

from app.application.reading.ports import IRepaginationQueue


class TaskiqRepaginationQueue(IRepaginationQueue):
    """Ставит задачу `repaginate_chapter` в default-очередь."""

    async def enqueue(self, chapter_id: int) -> None:
        # Ленивый импорт, чтобы избежать циклов при сборке контейнера.
        from app.infrastructure.tasks.repagination import repaginate_chapter

        await repaginate_chapter.kiq(chapter_id)
