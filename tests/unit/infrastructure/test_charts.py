"""Smoke-тесты рендера PNG-графиков."""

from __future__ import annotations

from datetime import date, datetime

from app.application.stats.ports import (
    CohortRow,
    DailyActivityRow,
    FunnelRow,
    ModeratorLoadRow,
    TopAuthorRow,
    TopFandomRow,
)
from app.infrastructure.stats.charts import (
    render_cohort_heatmap_png,
    render_daily_activity_png,
    render_funnel_png,
    render_moderator_load_png,
    render_top_authors_png,
    render_top_fandoms_png,
)

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def test_funnel_renders_png() -> None:
    row = FunnelRow(
        code="x",
        name="test",
        transitions=120,
        unique_users=100,
        registered=50,
        first_reads=25,
        first_publishes=5,
        blocked_bot=3,
    )
    png = render_funnel_png(row)
    assert png.startswith(_PNG_SIG)
    assert len(png) > 500


def test_daily_activity_renders_png() -> None:
    rows = [
        DailyActivityRow(
            day=date(2026, 4, 1),
            starts=10,
            registers=5,
            first_reads=3,
            first_publishes=1,
        ),
        DailyActivityRow(
            day=date(2026, 4, 2),
            starts=20,
            registers=10,
            first_reads=6,
            first_publishes=2,
        ),
    ]
    png = render_daily_activity_png(rows, "Test")
    assert png.startswith(_PNG_SIG)


def test_daily_activity_empty_still_renders() -> None:
    png = render_daily_activity_png([], "Empty")
    assert png.startswith(_PNG_SIG)


def test_top_fandoms_renders_png() -> None:
    rows = [TopFandomRow(fandom_id=i, fandom_name=f"F{i}", new_fics_7d=i) for i in range(1, 6)]
    png = render_top_fandoms_png(rows)
    assert png.startswith(_PNG_SIG)


def test_top_authors_renders_png() -> None:
    rows = [
        TopAuthorRow(
            author_id=i,
            author_nick=f"nick{i}",
            fics_count=i,
            likes_sum=i * 10,
            reads_completed_sum=i * 5,
            last_published_at=datetime(2026, 4, 1),
        )
        for i in range(1, 4)
    ]
    png = render_top_authors_png(rows)
    assert png.startswith(_PNG_SIG)


def test_moderator_load_renders_png() -> None:
    rows = [
        ModeratorLoadRow(
            moderator_id=i,
            author_nick=f"mod{i}",
            decisions_total=100 - i * 10,
            approved_count=80 - i * 10,
            rejected_count=20,
            avg_latency_seconds=float(3600 * i),
        )
        for i in range(1, 4)
    ]
    png = render_moderator_load_png(rows)
    assert png.startswith(_PNG_SIG)


def test_cohort_heatmap_renders_png() -> None:
    rows = [
        CohortRow(
            cohort_day=date(2026, 4, 1),
            size=100,
            d1=80,
            d7=50,
            d30=30,
        ),
        CohortRow(
            cohort_day=date(2026, 4, 2),
            size=120,
            d1=100,
            d7=60,
            d30=40,
        ),
    ]
    png = render_cohort_heatmap_png(rows)
    assert png.startswith(_PNG_SIG)
