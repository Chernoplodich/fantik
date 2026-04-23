"""Unit-тесты state-machine Broadcast."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.broadcasts.entities import Broadcast
from app.domain.broadcasts.exceptions import InvalidBroadcastTransitionError
from app.domain.broadcasts.value_objects import BroadcastStatus
from app.domain.shared.types import BroadcastId, UserId

_NOW = datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC)


def _make_draft() -> Broadcast:
    return Broadcast.new_draft(
        broadcast_id=BroadcastId(1),
        created_by=UserId(100),
        source_chat_id=100,
        source_message_id=50,
        now=_NOW,
    )


def test_new_draft_emits_created_event() -> None:
    bc = _make_draft()
    events = bc.pull_events()
    assert len(events) == 1
    assert events[0].name == "broadcast.created"
    assert bc.status == BroadcastStatus.DRAFT


def test_schedule_from_draft_ok() -> None:
    bc = _make_draft()
    bc.pull_events()
    at = datetime(2026, 4, 23, 13, 0, 0, tzinfo=UTC)
    bc.schedule(scheduled_at=at)
    assert bc.status == BroadcastStatus.SCHEDULED
    assert bc.scheduled_at == at
    events = bc.pull_events()
    assert any(e.name == "broadcast.scheduled" for e in events)


def test_launch_from_draft_ok() -> None:
    bc = _make_draft()
    bc.launch(now=_NOW)
    assert bc.status == BroadcastStatus.RUNNING
    assert bc.started_at == _NOW


def test_launch_from_scheduled_ok() -> None:
    bc = _make_draft()
    bc.schedule(scheduled_at=_NOW)
    bc.launch(now=_NOW)
    assert bc.status == BroadcastStatus.RUNNING


def test_cancel_from_running_ok() -> None:
    bc = _make_draft()
    bc.launch(now=_NOW)
    bc.cancel(actor_id=UserId(100), now=_NOW)
    assert bc.status == BroadcastStatus.CANCELLED
    assert bc.finished_at == _NOW


def test_cancel_from_draft_ok() -> None:
    bc = _make_draft()
    bc.cancel(actor_id=UserId(100), now=_NOW)
    assert bc.status == BroadcastStatus.CANCELLED


def test_cancel_from_terminal_raises() -> None:
    bc = _make_draft()
    bc.launch(now=_NOW)
    bc.mark_finished(stats={"total": 5, "sent": 5, "failed": 0, "blocked": 0}, now=_NOW)
    with pytest.raises(InvalidBroadcastTransitionError):
        bc.cancel(actor_id=UserId(100), now=_NOW)


def test_finished_from_running_ok() -> None:
    bc = _make_draft()
    bc.launch(now=_NOW)
    bc.mark_finished(stats={"total": 10, "sent": 9, "failed": 1, "blocked": 0}, now=_NOW)
    assert bc.status == BroadcastStatus.FINISHED
    assert bc.stats["total"] == 10


def test_finished_from_draft_raises() -> None:
    bc = _make_draft()
    with pytest.raises(InvalidBroadcastTransitionError):
        bc.mark_finished(stats={"total": 0}, now=_NOW)


def test_schedule_from_running_raises() -> None:
    bc = _make_draft()
    bc.launch(now=_NOW)
    with pytest.raises(InvalidBroadcastTransitionError):
        bc.schedule(scheduled_at=_NOW)


def test_set_keyboard_only_in_draft() -> None:
    bc = _make_draft()
    bc.set_keyboard([[{"text": "hi", "url": "https://example.com"}]])
    bc.launch(now=_NOW)
    with pytest.raises(InvalidBroadcastTransitionError):
        bc.set_keyboard(None)


def test_set_segment_only_in_draft() -> None:
    bc = _make_draft()
    bc.set_segment({"kind": "all"})
    bc.launch(now=_NOW)
    with pytest.raises(InvalidBroadcastTransitionError):
        bc.set_segment({"kind": "authors"})
