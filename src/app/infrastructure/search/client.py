"""Фабрика AsyncClient для Meilisearch. Singleton на процесс через DI."""

from __future__ import annotations

from meilisearch_python_sdk import AsyncClient

from app.core.config import Settings

INDEX_NAME = "fanfics"
PRIMARY_KEY = "id"


def build_meili_client(settings: Settings) -> AsyncClient:
    """Создать AsyncClient. Вызывающий обязан закрыть через `await client.aclose()`."""
    return AsyncClient(
        url=settings.meili_url,
        api_key=settings.meili_master_key.get_secret_value(),
    )
