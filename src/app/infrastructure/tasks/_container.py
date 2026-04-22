"""Ленивый singleton-контейнер для TaskIQ-задач.

Таски запускаются в своём процессе (taskiq worker); им нужен тот же DI-граф,
что и боту. Чтобы не собирать контейнер на каждое выполнение, храним ссылку
в module-level переменной — сборка выполнится один раз на первый вызов.
"""

from __future__ import annotations

from dishka import AsyncContainer

_container: AsyncContainer | None = None


def get_worker_container() -> AsyncContainer:
    """Вернуть singleton-контейнер. Потокобезопасно в рамках одного event loop."""
    global _container
    if _container is None:
        from app.core.di import build_container

        _container = build_container()
    return _container


async def close_worker_container() -> None:
    """Закрыть контейнер — на shutdown воркера (вызывается в tests/teardown)."""
    global _container
    if _container is not None:
        await _container.close()
        _container = None
