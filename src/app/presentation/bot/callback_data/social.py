"""Callback data для социальных функций: подписки и жалобы."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class SubNav(CallbackData, prefix="sn"):
    """Действия с подпиской на автора (из карточки фика).

    a:
      sub   — подписаться
      unsub — отписаться
    f: fic_id (автора резолвим по фику)
    """

    a: str
    f: int


class RepStart(CallbackData, prefix="rps"):
    """Запуск FSM жалобы из читалки / карточки.

    t:  target type — 'fic' | 'ch'
    id: target id — fic_id или chapter_id
    """

    t: str
    id: int


class RepReason(CallbackData, prefix="rpr"):
    """Выбор причины в FSM waiting_reason."""

    code: str


class RepMod(CallbackData, prefix="rpm"):
    """Действия модератора по жалобам.

    a:
      list      — показать список open
      card      — карточка одной жалобы
      dismiss   — Dismiss (отклонить жалобу)
      action    — Action (архивировать цель)
    id: report_id (для list=0)
    p:  page offset для list
    """

    a: str
    id: int = 0
    p: int = 0
