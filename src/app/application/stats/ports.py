"""Порты application-слоя для статистики."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class FunnelRow:
    """Воронка по UTM-коду.

    - transitions: всего кликов по ссылке (все `start` события по коду).
    - unique_users: сколько уникальных юзеров вообще перешли.
    - registered: приняли правила, создан профиль.
    - first_reads: начали читать хотя бы один фик.
    - first_publishes: опубликовали работу.
    - blocked_bot: из пришедших по коду — заблокировали бота.
    """

    code: str
    name: str
    transitions: int
    unique_users: int
    registered: int
    first_reads: int
    first_publishes: int
    blocked_bot: int


@dataclass(frozen=True, kw_only=True)
class DailyActivityRow:
    day: date
    starts: int
    registers: int
    first_reads: int
    first_publishes: int


@dataclass(frozen=True, kw_only=True)
class TopFandomRow:
    fandom_id: int
    fandom_name: str
    new_fics_7d: int


@dataclass(frozen=True, kw_only=True)
class TopAuthorRow:
    author_id: int
    author_nick: str | None
    fics_count: int
    likes_sum: int
    reads_completed_sum: int
    last_published_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class ModeratorLoadRow:
    moderator_id: int
    author_nick: str | None
    decisions_total: int
    approved_count: int
    rejected_count: int
    avg_latency_seconds: float


@dataclass(frozen=True, kw_only=True)
class CohortRow:
    cohort_day: date
    size: int
    d1: int
    d7: int
    d30: int


@dataclass(frozen=True, kw_only=True)
class DauWauMau:
    dau: int
    wau: int
    mau: int


@dataclass(frozen=True, kw_only=True)
class DayBreakdown:
    """Агрегаты за одни календарные сутки (МСК): новые / активные / заблокировавшие."""

    new: int
    active: int
    blocked: int


@dataclass(frozen=True, kw_only=True)
class UsersOverview:
    """Сводка по пользователям: total + таблица по дням."""

    total: int
    alive: int  # total − blocked_bot − banned
    blocked_bot: int
    banned: int
    # Таблица «новые | активные | заблокировавшие» — за сегодня / вчера / 7 / 30 дней.
    today: DayBreakdown
    yesterday: DayBreakdown
    last_7d: DayBreakdown
    last_30d: DayBreakdown


@dataclass(frozen=True, kw_only=True)
class UsersDailyPoint:
    """Точка для timeseries-графика: сколько новых / активных / заблокировавших за день.

    Активные считаются приближённо через `last_seen_at`: это последний визит юзера.
    Для «сегодня» показывает всех, кто заходил сегодня; для более ранних дней —
    только тех, кто не возвращался после (их last_seen_at остался в тех сутках).
    Даёт отличную интуицию при небольших данных; для точного DAU нужен
    сессионный лог (Stage 7 hardening).
    """

    day: date
    new: int
    active: int
    blocked: int


class IStatsReader(Protocol):
    async def funnel_by_code(self, *, code: str, days: int = 30) -> FunnelRow | None: ...

    async def daily_activity(self, *, days: int = 14) -> list[DailyActivityRow]: ...

    async def dau_wau_mau(self) -> DauWauMau: ...

    async def users_overview(self) -> UsersOverview: ...

    async def users_daily_series(self, *, days: int = 30) -> list[UsersDailyPoint]: ...

    async def top_fandoms_7d(self, *, limit: int = 10) -> list[TopFandomRow]: ...

    async def top_authors(self, *, limit: int = 10) -> list[TopAuthorRow]: ...

    async def moderator_load(self, *, days: int = 7) -> list[ModeratorLoadRow]: ...

    async def retention_cohort(self, *, days: int = 30) -> list[CohortRow]: ...
