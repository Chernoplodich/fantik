"""Идемпотентное применение настроек индекса Meilisearch.

Схема — [`docs/08-search-design.md`](../../../../docs/08-search-design.md).

Вызывается один раз при старте bot-процесса (best-effort). Meili сам диффит:
повторные вызовы с теми же настройками — no-op. Ошибки не роняют запуск.
"""

from __future__ import annotations

from meilisearch_python_sdk import AsyncClient
from meilisearch_python_sdk.errors import MeilisearchApiError
from meilisearch_python_sdk.models.settings import (
    Faceting,
    MeilisearchSettings,
    MinWordSizeForTypos,
    Pagination,
    TypoTolerance,
)

from app.core.logging import get_logger
from app.infrastructure.search.client import INDEX_NAME, PRIMARY_KEY

log = get_logger(__name__)


_STOP_WORDS = [
    # RU
    "и",
    "в",
    "во",
    "на",
    "не",
    "что",
    "как",
    "с",
    "со",
    "о",
    "об",
    "к",
    "по",
    "до",
    "для",
    "или",
    "но",
    "а",
    "же",
    "бы",
    "был",
    "была",
    # EN
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "to",
    "in",
    "is",
    "it",
    "for",
]

_SYNONYMS = {
    "хп": ["гарри поттер", "поттер"],
    "гп": ["гарри поттер", "поттер"],
    "марвел": ["marvel"],
    "мсв": ["mcu", "marvel"],
    "нс17": ["nc-17", "nc17"],
}


def _build_settings() -> MeilisearchSettings:
    """Собираем Pydantic-модель настроек индекса.

    SDK требует типизированные модели, а не dict — иначе `.model_dump()` в адаптере
    упадёт с 'dict has no attribute model_dump'.
    """
    return MeilisearchSettings(
        searchable_attributes=[
            "title",
            "author_nick",
            "summary",
            "tags",
            "characters",
            "fandom_name",
            "fandom_aliases",
            "chapters_text_excerpt",
        ],
        filterable_attributes=[
            "fandom_id",
            # fandom_name используется как фасет: Meili требует filterable-атрибут
            # для возврата facetDistribution (см. application/search/filter_builder.FACETS).
            "fandom_name",
            # Категория (anime/books/films/...) — для будущего фильтра «по разделу».
            # Прямо сейчас UI её не использует, но включаем, чтобы избежать второго
            # bootstrap'а при добавлении фильтра.
            "fandom_category",
            "age_rating",
            "age_rating_order",
            "tags",
            "characters",
            "warnings",
            "likes_count",
            "chars_count",
            "chapters_count",
        ],
        sortable_attributes=[
            "first_published_at",
            "updated_at",
            "likes_count",
            "views_count",
            "reads_completed_count",
            "chars_count",
        ],
        ranking_rules=[
            "words",
            "typo",
            "proximity",
            "attribute",
            "sort",
            "exactness",
            "likes_count:desc",
        ],
        typo_tolerance=TypoTolerance(
            enabled=True,
            min_word_size_for_typos=MinWordSizeForTypos(one_typo=4, two_typos=8),
            disable_on_attributes=["author_nick"],
        ),
        stop_words=_STOP_WORDS,
        synonyms=_SYNONYMS,
        faceting=Faceting(max_values_per_facet=200),
        pagination=Pagination(max_total_hits=5000),
        search_cutoff_ms=150,
    )


async def ensure_index(client: AsyncClient) -> None:
    """Создаёт индекс с primary_key='id', если его ещё нет (иначе — no-op).

    В SDK 7.x `create_index` сам ждёт завершения задачи и возвращает `AsyncIndex`,
    так что отдельный `wait_for_task` не нужен (атрибута `task_uid` на AsyncIndex нет).
    """
    try:
        await client.get_index(INDEX_NAME)
    except MeilisearchApiError:
        await client.create_index(uid=INDEX_NAME, primary_key=PRIMARY_KEY)
        log.info("meili_index_created", index=INDEX_NAME, primary_key=PRIMARY_KEY)


async def apply(client: AsyncClient) -> None:
    """Применить настройки индекса идемпотентно. Вызывается при старте bot-процесса."""
    await ensure_index(client)
    index = client.index(INDEX_NAME)
    task = await index.update_settings(_build_settings())
    await client.wait_for_task(task.task_uid)
    log.info("meili_settings_applied", index=INDEX_NAME)
