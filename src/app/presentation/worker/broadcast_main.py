"""Entrypoint воркера рассылок (broadcast queue)."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.tasks.broker import broadcast_broker

if __name__ == "__main__":
    setup_logging(get_settings())

    async def _idle() -> None:
        while True:
            await asyncio.sleep(60)

    asyncio.run(_idle())
