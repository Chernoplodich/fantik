"""Backfill `first_publish` / `first_read` событий для уже-существующих
approved-фиков и завершённых чтений.

Фоновая история: до этой миграции `RecordEventUseCase` существовал, но wiring
в `ApproveUseCase` / `ReadPageUseCase` отсутствовал, поэтому события
`first_publish` / `first_read` не писались. После починки wiring (новые
действия пишут события корректно) этот backfill догоняет историческую
активность, чтобы админ-воронка показывала реальные числа.

Что делаем:
- Для каждого автора одобренного фика без существующего `first_publish`-события:
  пишем одну запись со временем самого раннего `first_published_at` и
  `code_id` = `users.utm_source_code_id` автора.
- Для каждого юзера, у которого есть `reads_completed` для ЧУЖОЙ главы и нет
  `first_read`-события: пишем одну запись со временем самого раннего
  `completed_at` и `code_id` = `users.utm_source_code_id`.

Все backfill-события помечены `payload->>'backfill' = 'true'` — это маркер
для аудита и для downgrade (точечный DELETE без затрагивания live-событий).

Идемпотентность:
- INSERT'ы фильтруют через `NOT EXISTS` по существующим `tracking_events` —
  повторный запуск не задвоит данные.
- Партиционная таблица `tracking_events` (RANGE по `created_at`) уже имеет
  партиции `y2026m04`-`y2026m06`; даты событий полностью попадают в этот
  диапазон. Если в будущем дата окажется вне партиции, INSERT упадёт на
  default-партицию (которая существует) — потери данных не будет.

Revision ID: 0012_backfill_first_events
Revises: 0011_fandom_proposals
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_backfill_first_events"
down_revision: str | None = "0011_fandom_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- first_publish ----
    # Для каждого автора одобренного фика создаём ровно одну запись о его
    # самой ранней публикации. LATERAL JOIN отдаёт первый approved-фик
    # с непустым `first_published_at`. Anti-join `NOT EXISTS` гарантирует,
    # что у автора ещё нет такого события (страховка от повторного запуска
    # и от задвоения с уже корректно работающим live-wiring'ом).
    op.execute(
        """
        INSERT INTO tracking_events (code_id, user_id, event_type, payload, created_at)
        SELECT
            u.utm_source_code_id,
            u.id,
            'first_publish'::tracking_event_type,
            jsonb_build_object('fic_id', first_fic.id, 'backfill', true),
            first_fic.first_published_at
        FROM users u
        JOIN LATERAL (
            SELECT f.id, f.first_published_at
            FROM fanfics f
            WHERE f.author_id = u.id
              AND f.status = 'approved'
              AND f.first_published_at IS NOT NULL
            ORDER BY f.first_published_at ASC
            LIMIT 1
        ) first_fic ON TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM tracking_events e
            WHERE e.user_id = u.id AND e.event_type = 'first_publish'
        );
        """
    )

    # ---- first_read ----
    # Для каждого юзера, у которого есть завершённое чтение чужой главы,
    # пишем одно событие со временем самого раннего `completed_at`.
    # Фильтр `f.author_id != u.id` — чтение собственных фиков не считается
    # за first_read (тот же контракт, что и в живом ReadPageUseCase).
    op.execute(
        """
        INSERT INTO tracking_events (code_id, user_id, event_type, payload, created_at)
        SELECT
            u.utm_source_code_id,
            u.id,
            'first_read'::tracking_event_type,
            jsonb_build_object(
                'fic_id', first_read.fic_id,
                'chapter_id', first_read.chapter_id,
                'backfill', true
            ),
            first_read.completed_at
        FROM users u
        JOIN LATERAL (
            SELECT rc.chapter_id, c.fic_id, rc.completed_at
            FROM reads_completed rc
            JOIN chapters c ON c.id = rc.chapter_id
            JOIN fanfics f ON f.id = c.fic_id
            WHERE rc.user_id = u.id
              AND f.author_id != u.id
            ORDER BY rc.completed_at ASC
            LIMIT 1
        ) first_read ON TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM tracking_events e
            WHERE e.user_id = u.id AND e.event_type = 'first_read'
        );
        """
    )

    # После INSERT'ов имеет смысл обновить mv_daily_activity, но REFRESH
    # лучше делать через scheduler-tick (`refresh_materialized_views_tick` —
    # каждые 10 минут). Не блокируем миграцию длинным REFRESH.


def downgrade() -> None:
    # Точечно удаляем только те события, что мы вставили (по маркеру).
    # Никакие живые события (без `backfill=true` в payload) не трогаются.
    op.execute(
        """
        DELETE FROM tracking_events
        WHERE event_type IN ('first_publish', 'first_read')
          AND (payload ->> 'backfill') = 'true';
        """
    )
