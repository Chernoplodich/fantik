"""Создание ежемесячных партиций `tracking_events` и REFRESH материализованных представлений."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Имена MV, обновляемых периодически.
MATERIALIZED_VIEWS = (
    "mv_daily_activity",
    "mv_top_fandoms_7d",
    "mv_author_stats",
    "mv_moderator_load",
)


class PartitionMaintenanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_tracking_events_partitions(self, *, months_ahead: int = 2) -> int:
        """Создать партиции `tracking_events_yYYYYmMM` на N месяцев вперёд."""
        months = max(1, int(months_ahead))
        stmt = text(
            """
            DO $$
            DECLARE
                start_month DATE := DATE_TRUNC('month', NOW())::DATE;
                d DATE;
                part_name TEXT;
                i INT;
            BEGIN
                FOR i IN 0..:m LOOP
                    d := (start_month + (i || ' months')::INTERVAL)::DATE;
                    part_name := 'tracking_events_y' || to_char(d, 'YYYY')
                                 || 'm' || to_char(d, 'MM');
                    EXECUTE format(
                        'CREATE TABLE IF NOT EXISTS %I PARTITION OF tracking_events '
                        'FOR VALUES FROM (%L) TO (%L);',
                        part_name, d, (d + INTERVAL '1 month')::DATE
                    );
                END LOOP;
            END $$;
            """.replace(":m", str(months))
        )
        await self._s.execute(stmt)
        return months + 1

    async def refresh_materialized_view(self, name: str) -> None:
        """REFRESH CONCURRENTLY одного MV.

        CONCURRENTLY требует UNIQUE-индекс и что MV уже содержит данные после
        первого REFRESH; мы создаём `WITH DATA` в миграции — ок.
        """
        if name not in MATERIALIZED_VIEWS:
            raise ValueError(f"Неизвестный MV: {name!r}")
        # Имя проверено — безопасно интерполировать.
        await self._s.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}"))

    async def refresh_all_materialized_views(self) -> list[str]:
        refreshed: list[str] = []
        for mv in MATERIALIZED_VIEWS:
            await self.refresh_materialized_view(mv)
            refreshed.append(mv)
        return refreshed
