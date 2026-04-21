"""HTTP /healthz и /readyz + /metrics (prometheus)."""

from __future__ import annotations

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings


async def _healthz(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _readyz(request: web.Request) -> web.Response:
    engine: AsyncEngine = request.app["engine"]
    redis: Redis = request.app["redis"]
    checks: dict[str, bool] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["pg"] = True
    except Exception:  # noqa: BLE001
        checks["pg"] = False
    try:
        pong = await redis.ping()
        checks["redis"] = bool(pong)
    except Exception:  # noqa: BLE001
        checks["redis"] = False
    status = 200 if all(checks.values()) else 503
    return web.json_response(checks, status=status)


async def _metrics(_: web.Request) -> web.Response:
    data = generate_latest()
    return web.Response(body=data, content_type=CONTENT_TYPE_LATEST.split(";")[0])


def build_health_app(engine: AsyncEngine, redis: Redis, _settings: Settings) -> web.Application:
    app = web.Application()
    app["engine"] = engine
    app["redis"] = redis
    app.router.add_get("/healthz", _healthz)
    app.router.add_get("/readyz", _readyz)
    app.router.add_get("/metrics", _metrics)
    return app
