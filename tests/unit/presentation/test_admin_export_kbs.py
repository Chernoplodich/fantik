"""Кнопки выгрузки .txt с id пользователей в админке.

Покрываются:
- карточка трекинг-кода — кнопка `📥 Выгрузить ID (.txt)` с правильным
  callback_data (TrackingCD action=export_users + code_id);
- overview статистики — кнопка `📥 Выгрузить всех ID (.txt)` (StatsCD
  dashboard=export_users).
"""

from __future__ import annotations

from app.presentation.bot.callback_data.admin import StatsCD, TrackingCD
from app.presentation.bot.keyboards.admin_stats import build_stats_overview_kb
from app.presentation.bot.keyboards.admin_tracking import build_tracking_card_kb


def _flatten(kb: object) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append((btn.text, btn.callback_data or ""))
    return out


class TestTrackingCardExportButton:
    def test_active_card_has_export_button_with_code_id(self) -> None:
        kb = build_tracking_card_kb(code_id=42, active=True)
        items = _flatten(kb)
        export = next(((t, c) for t, c in items if "Выгрузить" in t), None)
        assert export is not None, "expected export button on active card"
        text, cb_data = export
        assert ".txt" in text
        cd = TrackingCD.unpack(cb_data)
        assert cd.action == "export_users"
        assert cd.code_id == 42

    def test_inactive_card_still_has_export(self) -> None:
        # Выгрузка должна работать и на отключённых ссылках — у них всё ещё
        # есть исторические переходы, по которым админ может захотеть выгрузить.
        kb = build_tracking_card_kb(code_id=99, active=False)
        items = _flatten(kb)
        assert any("Выгрузить" in t for t, _c in items)


class TestStatsOverviewExportButton:
    def test_export_users_button_present(self) -> None:
        kb = build_stats_overview_kb()
        items = _flatten(kb)
        export = next(((t, c) for t, c in items if "Выгрузить" in t), None)
        assert export is not None, "expected export-all button on stats overview"
        text, cb_data = export
        assert ".txt" in text
        cd = StatsCD.unpack(cb_data)
        assert cd.dashboard == "export_users"
