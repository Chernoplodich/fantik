"""CallbackData админского слоя."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class AdminCD(CallbackData, prefix="adm"):
    """Корневой роутинг админ-меню."""

    action: str  # root / broadcasts / tracking / stats / fandoms / proposals / tags / back


class BroadcastCD(CallbackData, prefix="bc"):
    action: str  # list / new / open / cancel / retry_failed / back
    bid: int = 0


class SegmentCD(CallbackData, prefix="bcseg"):
    kind: str  # all / active / authors / subscribers_of / utm
    value: int = 0  # для active_since_days — N; иначе 0


class ScheduleCD(CallbackData, prefix="bcsch"):
    kind: str  # now / schedule / cancel


class KeyboardChoiceCD(CallbackData, prefix="bckb"):
    choice: str  # yes / no


class ConfirmCD(CallbackData, prefix="bccf"):
    action: str  # ok / cancel


class TrackingCD(CallbackData, prefix="trk"):
    action: str  # list / new / open / deactivate / funnel / export_users
    code_id: int = 0


class StatsCD(CallbackData, prefix="st"):
    dashboard: str  # today / week / authors / fandoms / moderators / cohort / export_users


class FandomAdminCD(CallbackData, prefix="fd"):
    action: str  # list / new / open / toggle_active
    fandom_id: int = 0


class FandomProposalAdminCD(CallbackData, prefix="fdp"):
    """Админ-операции над заявкой на фандом.

    `cat` используется для двухшагового approve: pick → do.
    """

    action: str  # list / open / approve_pick / approve_do / reject
    pid: int = 0
    cat: str = ""


class TagAdminCD(CallbackData, prefix="tg"):
    action: str  # candidates / merge
    canonical_id: int = 0
    source_id: int = 0
