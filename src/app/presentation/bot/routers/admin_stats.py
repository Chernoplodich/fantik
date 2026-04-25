"""Роутер админских дашбордов статистики (admin only).

Главный экран — при клике «📊 Статистика» (или `/stats`) — сразу PNG-график
(новые/заблокировавшие за 30 дней) + caption с таблицей по суткам + кнопки
остальных дашбордов. Без лишних «Сегодня/Неделя» — они слиты в главный.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from app.application.stats.get_dashboard import (
    DashboardData,
    DashboardKind,
    GetDashboardCommand,
    GetDashboardUseCase,
)
from app.core.errors import DomainError
from app.core.logging import get_logger
from app.infrastructure.stats.charts import (
    render_cohort_heatmap_png,
    render_daily_activity_png,
    render_moderator_load_png,
    render_top_authors_png,
    render_top_fandoms_png,
    render_users_daily_png,
)
from app.presentation.bot.callback_data.admin import AdminCD, StatsCD
from app.presentation.bot.filters.role import IsAdmin
from app.presentation.bot.keyboards.admin_stats import (
    build_stats_back_kb,
    build_stats_overview_kb,
)
from app.presentation.bot.ui_helpers import render_photo

log = get_logger(__name__)
router = Router(name="admin_stats")


# ---------- entry: главный экран статистики ----------


@router.callback_query(AdminCD.filter(F.action == "stats"), IsAdmin())
@inject
async def show_stats_overview(
    cb: CallbackQuery,
    uc: FromDishka[GetDashboardUseCase],
) -> None:
    """Главный дашборд: график + таблица, без предварительного меню."""
    try:
        data = await uc(GetDashboardCommand(kind="overview"))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await _render_overview(event=cb, data=data)
    await cb.answer()


@router.message(Command("stats"), IsAdmin())
@inject
async def cmd_stats(
    message: Message,
    uc: FromDishka[GetDashboardUseCase],
) -> None:
    data = await uc(GetDashboardCommand(kind="overview"))
    await _render_overview(event=message, data=data)


@router.callback_query(StatsCD.filter(F.dashboard == "overview"), IsAdmin())
@inject
async def refresh_overview(
    cb: CallbackQuery,
    uc: FromDishka[GetDashboardUseCase],
) -> None:
    try:
        data = await uc(GetDashboardCommand(kind="overview"))
    except DomainError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await _render_overview(event=cb, data=data)
    await cb.answer("Обновлено")


# ---------- второстепенные дашборды ----------


@router.callback_query(StatsCD.filter(F.dashboard != "overview"), IsAdmin())
@inject
async def show_dashboard(
    cb: CallbackQuery,
    callback_data: StatsCD,
    uc: FromDishka[GetDashboardUseCase],
) -> None:
    kind: DashboardKind = callback_data.dashboard  # type: ignore[assignment]
    try:
        data = await uc(GetDashboardCommand(kind=kind))
    except (DomainError, ValueError) as e:
        await cb.answer(str(e), show_alert=True)
        return
    if kind == "tracking":
        await _render_tracking(cb=cb, data=data)
    elif kind == "authors":
        await _render_authors(cb=cb, data=data)
    elif kind == "fandoms":
        await _render_fandoms(cb=cb, data=data)
    elif kind == "moderators":
        await _render_moderators(cb=cb, data=data)
    elif kind == "cohort":
        await _render_cohort(cb=cb, data=data)
    await cb.answer()


# ---------- renderers ----------


async def _render_overview(*, event: CallbackQuery | Message, data: DashboardData) -> None:
    ov = data.users_overview
    series = data.users_series or []

    caption = _format_overview_caption(ov) if ov is not None else "📊 Статистика недоступна."

    png = render_users_daily_png(series, title="Новые и заблокировавшие — 30 дней")
    await render_photo(
        event,
        photo=BufferedInputFile(png, "users_30d.png"),
        caption=caption,
        reply_markup=build_stats_overview_kb(),
    )


def _format_overview_caption(ov) -> str:  # type: ignore[no-untyped-def]
    # Таблица: Новые / Активные / Заблок — 4 строки (сегодня/вчера/7д/30д).
    rows = [
        ("Сегодня", ov.today),
        ("Вчера", ov.yesterday),
        ("7 дней", ov.last_7d),
        ("30 дней", ov.last_30d),
    ]
    label_w = 8
    col_w = max(
        5,
        max(len(str(r[1].new)) for r in rows),
        max(len(str(r[1].active)) for r in rows),
        max(len(str(r[1].blocked)) for r in rows),
    )
    header = f"{'':<{label_w}}{'Новые':>{col_w}}  {'Активн':>{col_w}}  {'Блок':>{col_w}}"
    sep = "─" * len(header)
    body = "\n".join(
        f"{label:<{label_w}}{b.new:>{col_w}}  {b.active:>{col_w}}  {b.blocked:>{col_w}}"
        for label, b in rows
    )
    table = "<pre>" + "\n".join([header, sep, body]) + "</pre>"

    return (
        "📊 <b>Статистика</b>\n"
        f"👥 Всего: <b>{ov.total}</b>  "
        f"(🟢 Живых: <b>{ov.alive}</b>)\n"
        f"🚫 Заблокали: {ov.blocked_bot}  (🔒 Бан: {ov.banned})\n\n"
        f"{table}"
    )


async def _render_tracking(*, cb: CallbackQuery, data: DashboardData) -> None:
    """Старый трекинг-дашборд: переходы / регистрации / первые чтения / публикации."""
    rows = data.daily or []
    if rows:
        lines = ["📈 <b>Трекинг-события за 30 дней</b>", ""]
        total = {
            "starts": sum(r.starts for r in rows),
            "registers": sum(r.registers for r in rows),
            "first_reads": sum(r.first_reads for r in rows),
            "first_publishes": sum(r.first_publishes for r in rows),
        }
        lines.append(f"🔗 Переходов:        {total['starts']}")
        lines.append(f"📝 Регистраций:      {total['registers']}")
        lines.append(f"📖 Начали читать:    {total['first_reads']}")
        lines.append(f"✍️ Опубликовали:     {total['first_publishes']}")
        caption = "\n".join(lines)
    else:
        caption = (
            "📈 <b>Трекинг-события</b>\n\nДанных пока нет — никто не приходил по трекинг-ссылкам."
        )
    png = render_daily_activity_png(rows, "Трекинг-события — 30 дней")
    await render_photo(
        cb,
        photo=BufferedInputFile(png, "tracking_30d.png"),
        caption=caption,
        reply_markup=build_stats_back_kb(),
    )


async def _render_authors(*, cb: CallbackQuery, data: DashboardData) -> None:
    authors = data.authors or []
    if authors:
        lines = ["✍️ <b>Топ авторов по лайкам</b>", ""]
        for i, r in enumerate(authors, 1):
            lines.append(
                f"  {i}. {r.author_nick or f'#{r.author_id}'}: "
                f"лайков={r.likes_sum}, прочитано={r.reads_completed_sum}, "
                f"работ={r.fics_count}"
            )
        caption = "\n".join(lines)
    else:
        caption = "✍️ Топ авторов: данных пока нет"
    png = render_top_authors_png(authors)
    await render_photo(
        cb,
        photo=BufferedInputFile(png, "top_authors.png"),
        caption=caption,
        reply_markup=build_stats_back_kb(),
    )


async def _render_fandoms(*, cb: CallbackQuery, data: DashboardData) -> None:
    fandoms = data.fandoms or []
    if fandoms:
        lines = ["📚 <b>Топ фандомов за 7 дней</b>", ""]
        for i, r in enumerate(fandoms, 1):
            lines.append(f"  {i}. {r.fandom_name}: {r.new_fics_7d} новых")
        caption = "\n".join(lines)
    else:
        caption = "📚 Топ фандомов: данных пока нет"
    png = render_top_fandoms_png(fandoms)
    await render_photo(
        cb,
        photo=BufferedInputFile(png, "top_fandoms.png"),
        caption=caption,
        reply_markup=build_stats_back_kb(),
    )


async def _render_moderators(*, cb: CallbackQuery, data: DashboardData) -> None:
    mods = data.moderators or []
    if mods:
        lines = ["🛡️ <b>Нагрузка модераторов за 7 дней</b>", ""]
        for r in mods:
            lines.append(
                f"  {r.author_nick or f'#{r.moderator_id}'}: "
                f"решений={r.decisions_total} "
                f"(одобрено={r.approved_count}, отклонено={r.rejected_count}), "
                f"средняя скорость={r.avg_latency_seconds:.0f}с"
            )
        caption = "\n".join(lines)
    else:
        caption = "🛡️ Модераторы: данных пока нет"
    png = render_moderator_load_png(mods)
    await render_photo(
        cb,
        photo=BufferedInputFile(png, "mod_load.png"),
        caption=caption,
        reply_markup=build_stats_back_kb(),
    )


async def _render_cohort(*, cb: CallbackQuery, data: DashboardData) -> None:
    cohort = data.cohort or []
    if cohort:
        lines = ["🔁 <b>Retention по когортам</b>", ""]
        for r in cohort:
            size = max(r.size, 1)
            lines.append(
                f"  {r.cohort_day.strftime('%d.%m')}: размер={r.size}, "
                f"D1={r.d1} ({r.d1 / size * 100:.1f}%), "
                f"D7={r.d7} ({r.d7 / size * 100:.1f}%), "
                f"D30={r.d30} ({r.d30 / size * 100:.1f}%)"
            )
        caption = "\n".join(lines)
    else:
        caption = "🔁 Retention: данных пока нет"
    png = render_cohort_heatmap_png(cohort)
    await render_photo(
        cb,
        photo=BufferedInputFile(png, "cohort.png"),
        caption=caption,
        reply_markup=build_stats_back_kb(),
    )
