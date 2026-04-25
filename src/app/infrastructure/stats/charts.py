"""Рендер PNG-графиков через matplotlib (Agg backend).

Ленивый импорт matplotlib ВНУТРИ функций: иначе любой импорт этого модуля
инициализирует matplotlib с дефолтным backend'ом и тянет за собой GUI-части.
На bot-процессе это нежелательно (headless Docker).
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

from app.application.stats.ports import (
    CohortRow,
    DailyActivityRow,
    FunnelRow,
    ModeratorLoadRow,
    TopAuthorRow,
    TopFandomRow,
    UsersDailyPoint,
)


def _import_plt() -> tuple[Any, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return matplotlib, plt


def render_funnel_png(row: FunnelRow) -> bytes:
    _, plt = _import_plt()
    # `start` пишется только при первой регистрации, поэтому
    # transitions / unique_users / registered всегда равны — показываем один
    # бар «Новых пользователей» вместо трёх дублирующихся.
    labels = [
        "Новых пользователей",
        "Начали читать",
        "Опубликовали",
        "Заблокировали",
    ]
    values = [
        row.transitions,
        row.first_reads,
        row.first_publishes,
        row.blocked_bot,
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(
        labels,
        values,
        color=["#4C78A8", "#54A24B", "#B279A2", "#E45756"],
    )
    for bar, value in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(value),
            ha="center",
            va="bottom",
            fontsize=10,
        )
    ax.set_title(f"Воронка по коду «{row.code}» — {row.name}")
    ax.set_ylabel("Пользователи")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    return _fig_to_png(fig)


def render_users_daily_png(
    series: list[UsersDailyPoint], *, title: str = "Пользователи по дням"
) -> bytes:
    """Линии: новые / активные / заблокировавшие бота по дням."""
    _, plt = _import_plt()
    fig, ax = plt.subplots(figsize=(10, 5))
    if not series:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
    else:
        days = [p.day for p in series]
        new = [p.new for p in series]
        active = [p.active for p in series]
        blocked = [p.blocked for p in series]
        ax.plot(days, active, marker="o", label="Активные", color="#54A24B", linewidth=2)
        ax.fill_between(days, active, alpha=0.12, color="#54A24B")
        ax.plot(days, new, marker="o", label="Новые", color="#4C78A8")
        ax.plot(days, blocked, marker="s", label="Заблокировали", color="#E45756")
        ax.legend()
        fig.autofmt_xdate()
    ax.set_title(title)
    ax.set_ylabel("Пользователей за день")
    ax.grid(True, axis="y", linestyle="--", alpha=0.3)
    fig.tight_layout()
    return _fig_to_png(fig)


def render_daily_activity_png(rows: list[DailyActivityRow], title: str) -> bytes:
    _, plt = _import_plt()
    fig, ax = plt.subplots(figsize=(10, 5))
    if not rows:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
    else:
        days: list[date] = [r.day for r in rows]
        for series, label in (
            ([r.starts for r in rows], "Переходы"),
            ([r.registers for r in rows], "Регистрации"),
            ([r.first_reads for r in rows], "Начали читать"),
            ([r.first_publishes for r in rows], "Опубликовали"),
        ):
            ax.plot(days, series, marker="o", label=label)
        ax.legend()
        fig.autofmt_xdate()
    ax.set_title(title)
    ax.set_ylabel("Событий")
    fig.tight_layout()
    return _fig_to_png(fig)


def render_top_fandoms_png(rows: list[TopFandomRow]) -> bytes:
    _, plt = _import_plt()
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * max(len(rows), 1) + 1)))
    if not rows:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
    else:
        names = [r.fandom_name for r in rows]
        values = [r.new_fics_7d for r in rows]
        ax.barh(names[::-1], values[::-1], color="#4C78A8")
    ax.set_title("Топ фандомов (7 дней)")
    ax.set_xlabel("Новые работы")
    fig.tight_layout()
    return _fig_to_png(fig)


def render_top_authors_png(rows: list[TopAuthorRow]) -> bytes:
    _, plt = _import_plt()
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * max(len(rows), 1) + 1)))
    if not rows:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
    else:
        labels = [r.author_nick or f"#{r.author_id}" for r in rows]
        values = [r.likes_sum for r in rows]
        ax.barh(labels[::-1], values[::-1], color="#54A24B")
    ax.set_title("Топ авторов (по сумме лайков)")
    ax.set_xlabel("Лайки")
    fig.tight_layout()
    return _fig_to_png(fig)


def render_moderator_load_png(rows: list[ModeratorLoadRow]) -> bytes:
    _, plt = _import_plt()
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * max(len(rows), 1) + 1)))
    if not rows:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
    else:
        labels = [r.author_nick or f"#{r.moderator_id}" for r in rows]
        approved = [r.approved_count for r in rows]
        rejected = [r.rejected_count for r in rows]
        ax.barh(labels[::-1], approved[::-1], color="#54A24B", label="Одобрено")
        ax.barh(
            labels[::-1],
            rejected[::-1],
            left=approved[::-1],
            color="#E45756",
            label="Отклонено",
        )
        ax.legend()
    ax.set_title("Нагрузка на модераторов (7 дней)")
    ax.set_xlabel("Решений")
    fig.tight_layout()
    return _fig_to_png(fig)


def render_cohort_heatmap_png(rows: list[CohortRow]) -> bytes:
    _, plt = _import_plt()
    fig, ax = plt.subplots(figsize=(9, max(3, 0.4 * max(len(rows), 1) + 1)))
    if not rows:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
    else:
        labels = [str(r.cohort_day) for r in rows]
        d1 = [r.d1 / max(r.size, 1) * 100 for r in rows]
        d7 = [r.d7 / max(r.size, 1) * 100 for r in rows]
        d30 = [r.d30 / max(r.size, 1) * 100 for r in rows]
        x = list(range(len(rows)))
        width = 0.28
        ax.bar([i - width for i in x], d1, width=width, label="D1", color="#4C78A8")
        ax.bar(x, d7, width=width, label="D7", color="#F58518")
        ax.bar([i + width for i in x], d30, width=width, label="D30", color="#54A24B")
        ax.set_xticks(x, labels, rotation=45, ha="right")
        ax.set_ylabel("Retention, %")
        ax.legend()
    ax.set_title("Retention по когортам")
    fig.tight_layout()
    return _fig_to_png(fig)


def _fig_to_png(fig) -> bytes:  # type: ignore[no-untyped-def]
    _, plt = _import_plt()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
