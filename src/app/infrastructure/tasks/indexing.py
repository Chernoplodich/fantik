"""TaskIQ-задачи индексации Meilisearch.

- `index_fanfic(fic_id)` — идемпотентная upsert/delete-задача (читает статус фика
  внутри себя, решает что делать). Планируется из outbox-диспетчера и из
  ToggleLikeUseCase через `TaskiqSearchIndexQueue`.
- `delete_from_index(fic_id)` — прямой delete без чтения PG (редко, на случай
  ручной чистки).
- `full_reindex()` — прогон по всем approved-фикам батчами. Вызывается вручную
  (admin-инструмент в этапе 6).
"""

from __future__ import annotations

from meilisearch_python_sdk import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.search.index_fanfic import (
    IndexFanficCommand,
    IndexFanficUseCase,
)
from app.application.search.ports import ISearchIndex
from app.core.logging import get_logger
from app.domain.fanfics.value_objects import FicStatus
from app.infrastructure.db.models.fanfic import Fanfic as FanficModel
from app.infrastructure.search.client import INDEX_NAME
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broker

log = get_logger(__name__)

_REINDEX_PAGE = 200


@broker.task(task_name="index_fanfic")
async def index_fanfic(fic_id: int) -> None:
    """Обёртка над IndexFanficUseCase для TaskIQ."""
    container = get_worker_container()
    async with container() as scope:
        uc = await scope.get(IndexFanficUseCase)
        await uc(IndexFanficCommand(fic_id=int(fic_id)))


@broker.task(task_name="delete_from_index")
async def delete_from_index(fic_id: int) -> None:
    container = get_worker_container()
    async with container() as scope:
        index = await scope.get(ISearchIndex)
        await index.delete(int(fic_id))
    log.info("delete_from_index_done", fic_id=int(fic_id))


@broker.task(task_name="full_reindex")
async def full_reindex() -> int:
    """Переиндексировать все approved-фики через IndexFanficUseCase.

    Читает id'шники батчами по `_REINDEX_PAGE`, на каждый вызывает use case
    (который сам делает upsert). Возвращает число обработанных.
    """
    container = get_worker_container()
    total = 0
    async with container() as scope:
        session = await scope.get(AsyncSession)

        offset = 0
        while True:
            stmt = (
                select(FanficModel.id)
                .where(FanficModel.status == FicStatus.APPROVED)
                .order_by(FanficModel.id.asc())
                .limit(_REINDEX_PAGE)
                .offset(offset)
            )
            ids = list((await session.execute(stmt)).scalars().all())
            if not ids:
                break

            uc = await scope.get(IndexFanficUseCase)
            for fid in ids:
                await uc(IndexFanficCommand(fic_id=int(fid)))

            total += len(ids)
            offset += _REINDEX_PAGE

    log.info("full_reindex_done", total=total)
    return total


# --- дополнительный guard: позволяет удалить индекс целиком (для тестов / ручной чистки).


async def purge_index_for_tests(client: AsyncClient) -> None:
    try:
        task = await client.index(INDEX_NAME).delete_all_documents()
        await client.wait_for_task(task.task_uid)
    except Exception as e:
        log.warning("purge_index_failed", error=str(e))
