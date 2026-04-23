"""Use case: получить данные для одного из админских дашбордов."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.application.stats.ports import (
    CohortRow,
    DailyActivityRow,
    DauWauMau,
    IStatsReader,
    ModeratorLoadRow,
    TopAuthorRow,
    TopFandomRow,
    UsersDailyPoint,
    UsersOverview,
)

DashboardKind = Literal[
    "overview", "tracking", "authors", "fandoms", "moderators", "cohort"
]


@dataclass(frozen=True, kw_only=True)
class DashboardData:
    kind: DashboardKind
    daily: list[DailyActivityRow] | None = None
    dau_wau_mau: DauWauMau | None = None
    users_overview: UsersOverview | None = None
    users_series: list[UsersDailyPoint] | None = None
    authors: list[TopAuthorRow] | None = None
    fandoms: list[TopFandomRow] | None = None
    moderators: list[ModeratorLoadRow] | None = None
    cohort: list[CohortRow] | None = None


@dataclass(frozen=True, kw_only=True)
class GetDashboardCommand:
    kind: DashboardKind


class GetDashboardUseCase:
    def __init__(self, reader: IStatsReader) -> None:
        self._reader = reader

    async def __call__(self, cmd: GetDashboardCommand) -> DashboardData:
        if cmd.kind == "overview":
            return DashboardData(
                kind=cmd.kind,
                users_overview=await self._reader.users_overview(),
                users_series=await self._reader.users_daily_series(days=30),
            )
        if cmd.kind == "tracking":
            return DashboardData(
                kind=cmd.kind,
                daily=await self._reader.daily_activity(days=30),
            )
        if cmd.kind == "authors":
            return DashboardData(
                kind=cmd.kind, authors=await self._reader.top_authors(limit=10)
            )
        if cmd.kind == "fandoms":
            return DashboardData(
                kind=cmd.kind, fandoms=await self._reader.top_fandoms_7d(limit=10)
            )
        if cmd.kind == "moderators":
            return DashboardData(
                kind=cmd.kind, moderators=await self._reader.moderator_load(days=7)
            )
        if cmd.kind == "cohort":
            return DashboardData(
                kind=cmd.kind, cohort=await self._reader.retention_cohort(days=30)
            )
        raise ValueError(f"Неизвестный dashboard: {cmd.kind!r}")
