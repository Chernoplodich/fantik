"""Load: рассылка на 50k получателей.

Не locust (тут HTTP не при чём — мы гоняем TaskIQ), а python-скрипт:

1. seed 50k users (batch INSERT).
2. прогон `CreateBroadcastDraft → Schedule(now) → Launch`.
3. ждём, пока `broadcasts.status = 'finished'` (или timeout).
4. печатаем отчёт: wall_clock, sent/blocked/failed.

Запуск (при поднятом стэке с `--profile loadtest`):
    uv run python -m tests.load.load_broadcast

Через Makefile: `make load-broadcast`.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

_RECIPIENTS = int(os.environ.get("LOAD_BROADCAST_RECIPIENTS", "50000"))
_TIMEOUT_S = int(os.environ.get("LOAD_BROADCAST_TIMEOUT_S", "3600"))
_PG = os.environ.get("LOAD_PG_DSN") or os.environ.get(
    "POSTGRES_URL",
    "postgresql+asyncpg://fantik:fantik@localhost:5432/fantik",
)


async def _seed_users(s: AsyncSession, n: int) -> None:
    # Быстрый массовый insert. Пропускаем конфликты, чтобы скрипт был идемпотентным.
    await s.execute(
        text(
            """
            INSERT INTO users (id, role, agreed_at, created_at, last_seen_at)
            SELECT 9_000_000_000 + i,
                   'user',
                   now(),
                   now(),
                   now()
              FROM generate_series(1, :n) AS s(i)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"n": n},
    )


async def _launch_broadcast(s: AsyncSession) -> int:
    row = await s.execute(
        text(
            """
            INSERT INTO broadcasts (
                status, created_by, source_chat_id, source_message_id,
                keyboard, segment, segment_params, scheduled_at, created_at
            ) VALUES (
                'scheduled', 1, 1, 1,
                NULL, 'all_active', '{}'::jsonb, now(), now()
            ) RETURNING id
            """
        )
    )
    bc_id = int(row.scalar_one())
    return bc_id


async def main() -> None:
    engine = create_async_engine(_PG)
    started = time.monotonic()
    async with engine.connect() as conn:
        async with conn.begin():
            await _seed_users(conn, _RECIPIENTS)  # type: ignore[arg-type]
        async with conn.begin():
            bc_id = await _launch_broadcast(conn)  # type: ignore[arg-type]
            print(f"[load-broadcast] created broadcast id={bc_id}, recipients~{_RECIPIENTS}")

        deadline = time.monotonic() + _TIMEOUT_S
        while time.monotonic() < deadline:
            res = await conn.execute(
                text("SELECT status FROM broadcasts WHERE id = :id"), {"id": bc_id}
            )
            status = res.scalar_one_or_none()
            if status in {"finished", "cancelled", "failed"}:
                break
            await asyncio.sleep(5)

        stats = (
            await conn.execute(
                text(
                    """
                    SELECT status, count(*) AS c
                      FROM broadcast_deliveries
                     WHERE broadcast_id = :id
                     GROUP BY status
                    """
                ),
                {"id": bc_id},
            )
        ).all()
        report = {row.status: row.c for row in stats}
        took = time.monotonic() - started
        print(f"[load-broadcast] final status={status!r}, took={took:.1f}s")
        print(f"[load-broadcast] deliveries breakdown: {report}")

    await engine.dispose()

    expected = _RECIPIENTS
    sent = report.get("sent", 0)
    # SLA: доставлено > 99% (остальное — blocked/failed допустимо).
    ok = sent >= int(expected * 0.99) and status == "finished"
    print("[load-broadcast] OK" if ok else "[load-broadcast] FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
