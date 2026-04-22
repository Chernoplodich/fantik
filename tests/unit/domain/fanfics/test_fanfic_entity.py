"""Unit-тесты агрегата Fanfic: переходы статусов."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.fanfics.entities import Fanfic
from app.domain.fanfics.exceptions import WrongStatusError
from app.domain.fanfics.value_objects import (
    FanficTitle,
    FicStatus,
    Summary,
)
from app.domain.shared.types import FandomId, FanficVersionId, UserId


def _make_fic() -> Fanfic:
    now = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)
    return Fanfic.create_draft(
        author_id=UserId(1),
        title=FanficTitle("Test work"),
        summary=Summary("Short summary"),
        summary_entities=[],
        fandom_id=FandomId(1),
        age_rating_id=1,
        cover_file_id=None,
        cover_file_unique_id=None,
        now=now,
    )


NOW = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)


class TestFanficLifecycle:
    def test_initial_status_is_draft(self) -> None:
        fic = _make_fic()
        assert fic.status == FicStatus.DRAFT

    def test_submit_from_draft(self) -> None:
        fic = _make_fic()
        fic.submit_for_review(now=NOW)
        assert fic.status == FicStatus.PENDING
        evts = fic.pull_events()
        assert any(e.__class__.__name__ == "FanficSubmitted" for e in evts)

    def test_approve_sets_first_published_at_only_first_time(self) -> None:
        fic = _make_fic()
        fic.submit_for_review(now=NOW)
        fic.approve(version_id=FanficVersionId(1), now=NOW)
        first = fic.first_published_at
        assert first == NOW
        # повторный approve не сбрасывает first_published_at
        fic.status = FicStatus.PENDING
        fic.approve(version_id=FanficVersionId(2), now=datetime(2026, 5, 1, tzinfo=UTC))
        assert fic.first_published_at == first

    def test_reject_requires_pending(self) -> None:
        fic = _make_fic()
        with pytest.raises(WrongStatusError):
            fic.reject(reason_ids=[1], now=NOW)
        fic.submit_for_review(now=NOW)
        fic.reject(reason_ids=[1], now=NOW)
        assert fic.status == FicStatus.REJECTED

    def test_revise_requires_rejected(self) -> None:
        fic = _make_fic()
        with pytest.raises(WrongStatusError):
            fic.mark_revising(now=NOW)
        fic.submit_for_review(now=NOW)
        fic.reject(reason_ids=[1], now=NOW)
        fic.mark_revising(now=NOW)
        assert fic.status == FicStatus.REVISING

    def test_update_meta_blocked_in_approved(self) -> None:
        fic = _make_fic()
        fic.submit_for_review(now=NOW)
        fic.approve(version_id=FanficVersionId(1), now=NOW)
        with pytest.raises(WrongStatusError):
            fic.update_meta(
                title=FanficTitle("New title"),
                summary=Summary("x"),
                summary_entities=[],
                fandom_id=FandomId(1),
                age_rating_id=1,
                cover_file_id=None,
                cover_file_unique_id=None,
                now=NOW,
            )

    def test_update_meta_ok_in_draft(self) -> None:
        fic = _make_fic()
        fic.update_meta(
            title=FanficTitle("Renamed"),
            summary=Summary("s"),
            summary_entities=[],
            fandom_id=FandomId(1),
            age_rating_id=1,
            cover_file_id=None,
            cover_file_unique_id=None,
            now=NOW,
        )
        assert str(fic.title) == "Renamed"

    def test_cancel_submission_only_from_pending(self) -> None:
        fic = _make_fic()
        with pytest.raises(WrongStatusError):
            fic.cancel_submission(now=NOW)
        fic.submit_for_review(now=NOW)
        fic.cancel_submission(now=NOW)
        assert fic.status == FicStatus.DRAFT
