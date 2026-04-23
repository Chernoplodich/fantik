"""PgStatsReader: чтение дашбордовых агрегатов.

Часть запросов идёт из materialized views, часть — ad-hoc (воронка, cohort).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.stats.ports import (
    CohortRow,
    DailyActivityRow,
    DauWauMau,
    DayBreakdown,
    FunnelRow,
    IStatsReader,
    ModeratorLoadRow,
    TopAuthorRow,
    TopFandomRow,
    UsersDailyPoint,
    UsersOverview,
)


class PgStatsReader(IStatsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def funnel_by_code(
        self, *, code: str, days: int = 30
    ) -> FunnelRow | None:
        # Основной запрос — события по коду (переходы/регистрации/...).
        stmt = text(
            """
            SELECT
              c.id AS code_id,
              c.code,
              c.name,
              COALESCE(count(*)
                FILTER (WHERE e.event_type='start'), 0) AS transitions,
              COALESCE(count(DISTINCT e.user_id)
                FILTER (WHERE e.event_type='start'), 0) AS unique_users,
              COALESCE(count(DISTINCT e.user_id)
                FILTER (WHERE e.event_type='register'), 0) AS registered,
              COALESCE(count(DISTINCT e.user_id)
                FILTER (WHERE e.event_type='first_read'), 0) AS first_reads,
              COALESCE(count(DISTINCT e.user_id)
                FILTER (WHERE e.event_type='first_publish'), 0) AS first_publishes
            FROM tracking_codes c
            LEFT JOIN tracking_events e
              ON e.code_id = c.id
             AND e.created_at > now() - make_interval(days => :d)
            WHERE c.code = :code
            GROUP BY c.id, c.code, c.name
            """
        )
        row = (await self._s.execute(stmt, {"code": code, "d": int(days)})).one_or_none()
        if row is None:
            return None

        # Заблокировавшие бота среди first-touch-пришедших по этому коду
        # (users.utm_source_code_id не перезаписывается — first-touch).
        blocked_stmt = text(
            """
            SELECT count(*) AS blocked
              FROM users
             WHERE utm_source_code_id = :code_id
               AND blocked_bot_at IS NOT NULL
            """
        )
        blocked = (
            await self._s.execute(blocked_stmt, {"code_id": int(row.code_id)})
        ).scalar_one()

        return FunnelRow(
            code=row.code,
            name=row.name,
            transitions=int(row.transitions),
            unique_users=int(row.unique_users),
            registered=int(row.registered),
            first_reads=int(row.first_reads),
            first_publishes=int(row.first_publishes),
            blocked_bot=int(blocked or 0),
        )

    async def daily_activity(self, *, days: int = 14) -> list[DailyActivityRow]:
        stmt = text(
            """
            SELECT day, starts, registers, first_reads, first_publishes
              FROM mv_daily_activity
             WHERE day > (now() AT TIME ZONE 'UTC')::date - make_interval(days => :d)
             ORDER BY day
            """
        )
        rows = (await self._s.execute(stmt, {"d": int(days)})).all()
        return [
            DailyActivityRow(
                day=r.day,
                starts=int(r.starts),
                registers=int(r.registers),
                first_reads=int(r.first_reads),
                first_publishes=int(r.first_publishes),
            )
            for r in rows
        ]

    async def dau_wau_mau(self) -> DauWauMau:
        # DAU/WAU/MAU считаем по фактической активности (`last_seen_at`
        # обновляется middleware user_upsert на каждом апдейте) — это
        # точнее, чем tracking_events, который пишется только на onboarding.
        stmt = text(
            """
            SELECT
              count(*) FILTER (WHERE last_seen_at > now() - interval '1 day')   AS dau,
              count(*) FILTER (WHERE last_seen_at > now() - interval '7 days')  AS wau,
              count(*) FILTER (WHERE last_seen_at > now() - interval '30 days') AS mau
              FROM users
             WHERE banned_at IS NULL
               AND blocked_bot_at IS NULL
            """
        )
        row = (await self._s.execute(stmt)).one()
        return DauWauMau(
            dau=int(row.dau or 0), wau=int(row.wau or 0), mau=int(row.mau or 0)
        )

    async def users_overview(self) -> UsersOverview:
        """Сводка: total + таблица [сегодня / вчера / 7 дней] по МСК.

        Новые — created_at попадает в окно.
        Активные — last_seen_at попадает в окно.
        Заблокировавшие — blocked_bot_at попадает в окно.

        «Сегодня» = с 00:00 МСК (Europe/Moscow) до now.
        «Вчера» = [−1 день 00:00 МСК, 00:00 МСК сегодня).
        «7 дней» = последние 7 суток скользящим окном.
        """
        stmt = text(
            """
            WITH bounds AS (
              SELECT
                date_trunc('day', now() AT TIME ZONE 'Europe/Moscow')
                  AT TIME ZONE 'Europe/Moscow' AS today_start,
                date_trunc('day', now() AT TIME ZONE 'Europe/Moscow')
                  AT TIME ZONE 'Europe/Moscow' - interval '1 day' AS yest_start,
                now() - interval '7 days'  AS seven_start,
                now() - interval '30 days' AS thirty_start
            )
            SELECT
              (SELECT count(*) FROM users)                            AS total,
              (SELECT count(*) FROM users WHERE blocked_bot_at IS NOT NULL) AS blocked_bot,
              (SELECT count(*) FROM users WHERE banned_at IS NOT NULL)      AS banned,

              (SELECT count(*) FROM users, bounds
                 WHERE created_at >= bounds.today_start)              AS new_today,
              (SELECT count(*) FROM users, bounds
                 WHERE last_seen_at >= bounds.today_start)            AS active_today,
              (SELECT count(*) FROM users, bounds
                 WHERE blocked_bot_at >= bounds.today_start)          AS blocked_today,

              (SELECT count(*) FROM users, bounds
                 WHERE created_at >= bounds.yest_start
                   AND created_at  < bounds.today_start)              AS new_yest,
              (SELECT count(*) FROM users, bounds
                 WHERE last_seen_at >= bounds.yest_start
                   AND last_seen_at  < bounds.today_start)            AS active_yest,
              (SELECT count(*) FROM users, bounds
                 WHERE blocked_bot_at >= bounds.yest_start
                   AND blocked_bot_at  < bounds.today_start)          AS blocked_yest,

              (SELECT count(*) FROM users, bounds
                 WHERE created_at >= bounds.seven_start)              AS new_7d,
              (SELECT count(*) FROM users, bounds
                 WHERE last_seen_at >= bounds.seven_start)            AS active_7d,
              (SELECT count(*) FROM users, bounds
                 WHERE blocked_bot_at >= bounds.seven_start)          AS blocked_7d,

              (SELECT count(*) FROM users, bounds
                 WHERE created_at >= bounds.thirty_start)             AS new_30d,
              (SELECT count(*) FROM users, bounds
                 WHERE last_seen_at >= bounds.thirty_start)           AS active_30d,
              (SELECT count(*) FROM users, bounds
                 WHERE blocked_bot_at >= bounds.thirty_start)         AS blocked_30d
            """
        )
        row = (await self._s.execute(stmt)).one()
        total = int(row.total or 0)
        blocked = int(row.blocked_bot or 0)
        banned = int(row.banned or 0)
        return UsersOverview(
            total=total,
            alive=max(0, total - blocked - banned),
            blocked_bot=blocked,
            banned=banned,
            today=DayBreakdown(
                new=int(row.new_today or 0),
                active=int(row.active_today or 0),
                blocked=int(row.blocked_today or 0),
            ),
            yesterday=DayBreakdown(
                new=int(row.new_yest or 0),
                active=int(row.active_yest or 0),
                blocked=int(row.blocked_yest or 0),
            ),
            last_7d=DayBreakdown(
                new=int(row.new_7d or 0),
                active=int(row.active_7d or 0),
                blocked=int(row.blocked_7d or 0),
            ),
            last_30d=DayBreakdown(
                new=int(row.new_30d or 0),
                active=int(row.active_30d or 0),
                blocked=int(row.blocked_30d or 0),
            ),
        )

    async def users_daily_series(
        self, *, days: int = 30
    ) -> list[UsersDailyPoint]:
        """Таймсерия по дням МСК: новые / активные / заблокировавшие.

        Генерим все дни в диапазоне (даже пустые), чтобы график не зиял дырами.
        «Активные за день» = дата последнего визита попадает в этот день
        (приближение; для точного DAU нужен сессионный лог).
        """
        stmt = text(
            """
            WITH d AS (
              SELECT generate_series(
                (date_trunc('day', now() AT TIME ZONE 'Europe/Moscow'))::date
                    - make_interval(days => :d - 1),
                (date_trunc('day', now() AT TIME ZONE 'Europe/Moscow'))::date,
                interval '1 day'
              )::date AS day
            ),
            new_per_day AS (
              SELECT (created_at AT TIME ZONE 'Europe/Moscow')::date AS day,
                     count(*) AS c
                FROM users
               WHERE created_at > now() - make_interval(days => :d + 1)
               GROUP BY 1
            ),
            active_per_day AS (
              SELECT (last_seen_at AT TIME ZONE 'Europe/Moscow')::date AS day,
                     count(*) AS c
                FROM users
               WHERE last_seen_at > now() - make_interval(days => :d + 1)
               GROUP BY 1
            ),
            blocked_per_day AS (
              SELECT (blocked_bot_at AT TIME ZONE 'Europe/Moscow')::date AS day,
                     count(*) AS c
                FROM users
               WHERE blocked_bot_at IS NOT NULL
                 AND blocked_bot_at > now() - make_interval(days => :d + 1)
               GROUP BY 1
            )
            SELECT d.day,
                   COALESCE(n.c, 0) AS new,
                   COALESCE(a.c, 0) AS active,
                   COALESCE(b.c, 0) AS blocked
              FROM d
              LEFT JOIN new_per_day     n ON n.day = d.day
              LEFT JOIN active_per_day  a ON a.day = d.day
              LEFT JOIN blocked_per_day b ON b.day = d.day
             ORDER BY d.day
            """
        )
        rows = (await self._s.execute(stmt, {"d": int(days)})).all()
        return [
            UsersDailyPoint(
                day=r.day,
                new=int(r.new),
                active=int(r.active),
                blocked=int(r.blocked),
            )
            for r in rows
        ]

    async def top_fandoms_7d(self, *, limit: int = 10) -> list[TopFandomRow]:
        stmt = text(
            """
            SELECT fandom_id, fandom_name, new_fics_7d
              FROM mv_top_fandoms_7d
             ORDER BY new_fics_7d DESC
             LIMIT :lim
            """
        )
        rows = (await self._s.execute(stmt, {"lim": int(limit)})).all()
        return [
            TopFandomRow(
                fandom_id=int(r.fandom_id),
                fandom_name=str(r.fandom_name),
                new_fics_7d=int(r.new_fics_7d),
            )
            for r in rows
        ]

    async def top_authors(self, *, limit: int = 10) -> list[TopAuthorRow]:
        stmt = text(
            """
            SELECT a.author_id, u.author_nick,
                   a.fics_count, a.likes_sum, a.reads_completed_sum, a.last_published_at
              FROM mv_author_stats a
              JOIN users u ON u.id = a.author_id
             ORDER BY a.likes_sum DESC, a.reads_completed_sum DESC
             LIMIT :lim
            """
        )
        rows = (await self._s.execute(stmt, {"lim": int(limit)})).all()
        return [
            TopAuthorRow(
                author_id=int(r.author_id),
                author_nick=r.author_nick,
                fics_count=int(r.fics_count),
                likes_sum=int(r.likes_sum),
                reads_completed_sum=int(r.reads_completed_sum),
                last_published_at=r.last_published_at,
            )
            for r in rows
        ]

    async def moderator_load(self, *, days: int = 7) -> list[ModeratorLoadRow]:
        stmt = text(
            """
            SELECT m.moderator_id, u.author_nick,
                   sum(m.decisions_total)::bigint AS decisions_total,
                   sum(m.approved_count)::bigint AS approved_count,
                   sum(m.rejected_count)::bigint AS rejected_count,
                   COALESCE(avg(m.avg_latency_seconds), 0)::double precision AS avg_latency_seconds
              FROM mv_moderator_load m
              JOIN users u ON u.id = m.moderator_id
             WHERE m.day > (now() AT TIME ZONE 'UTC')::date - make_interval(days => :d)
             GROUP BY m.moderator_id, u.author_nick
             ORDER BY decisions_total DESC
            """
        )
        rows = (await self._s.execute(stmt, {"d": int(days)})).all()
        return [
            ModeratorLoadRow(
                moderator_id=int(r.moderator_id),
                author_nick=r.author_nick,
                decisions_total=int(r.decisions_total or 0),
                approved_count=int(r.approved_count or 0),
                rejected_count=int(r.rejected_count or 0),
                avg_latency_seconds=float(r.avg_latency_seconds or 0.0),
            )
            for r in rows
        ]

    async def retention_cohort(self, *, days: int = 30) -> list[CohortRow]:
        stmt = text(
            """
            WITH cohorts AS (
              SELECT id, date_trunc('day', created_at AT TIME ZONE 'UTC')::date AS cohort_day
                FROM users
               WHERE created_at > now() - make_interval(days => :d)
            )
            SELECT
              c.cohort_day,
              count(*) AS size,
              count(*) FILTER (WHERE u.last_seen_at >= c.cohort_day + interval '1 day')  AS d1,
              count(*) FILTER (WHERE u.last_seen_at >= c.cohort_day + interval '7 days') AS d7,
              count(*) FILTER (WHERE u.last_seen_at >= c.cohort_day + interval '30 days') AS d30
              FROM cohorts c
              JOIN users u ON u.id = c.id
             GROUP BY c.cohort_day
             ORDER BY c.cohort_day
            """
        )
        rows = (await self._s.execute(stmt, {"d": int(days)})).all()
        return [
            CohortRow(
                cohort_day=r.cohort_day,
                size=int(r.size),
                d1=int(r.d1),
                d7=int(r.d7),
                d30=int(r.d30),
            )
            for r in rows
        ]
