"""Unit-тест CancelSubmissionUseCase."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.fanfics.add_chapter import (
    AddChapterCommand,
    AddChapterUseCase,
)
from app.application.fanfics.cancel_submission import (
    CancelSubmissionCommand,
    CancelSubmissionUseCase,
)
from app.application.fanfics.create_draft import (
    CreateDraftCommand,
    CreateDraftUseCase,
)
from app.application.fanfics.submit_for_review import (
    SubmitForReviewCommand,
    SubmitForReviewUseCase,
)
from app.core.clock import FrozenClock
from app.core.config import get_settings
from app.domain.fanfics.value_objects import FicStatus
from app.domain.moderation.exceptions import CaseBeingReviewedError
from app.domain.shared.types import FanficId, UserId

from ._fakes import (
    FakeChapters,
    FakeFanfics,
    FakeModeration,
    FakeOutbox,
    FakeReference,
    FakeTags,
    FakeUow,
    FakeUsers,
    FakeVersions,
    make_user,
)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC))


async def _submit(clock: FrozenClock) -> dict:
    users = FakeUsers()
    users.add(make_user(tg_id=1))
    fanfics = FakeFanfics()
    chapters = FakeChapters()
    tags = FakeTags()
    ref = FakeReference()
    versions = FakeVersions()
    moderation = FakeModeration()
    outbox = FakeOutbox()
    settings = get_settings()

    create = CreateDraftUseCase(FakeUow(), fanfics, tags, ref, users, clock)
    draft = await create(
        CreateDraftCommand(
            author_id=1,
            title="Title",
            summary="S",
            summary_entities=[],
            fandom_id=1,
            age_rating_id=1,
            tag_raws=[],
        )
    )
    add_ch = AddChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
    await add_ch(
        AddChapterCommand(fic_id=draft.fic_id, author_id=1, title="C", text="t", entities=[])
    )
    submit = SubmitForReviewUseCase(
        FakeUow(),
        fanfics,
        chapters,
        versions,
        moderation,
        outbox,
        users,
        clock,
        settings,
    )
    await submit(SubmitForReviewCommand(fic_id=draft.fic_id, author_id=1))
    return {
        "fic_id": draft.fic_id,
        "fanfics": fanfics,
        "chapters": chapters,
        "moderation": moderation,
    }


class TestCancelSubmission:
    async def test_happy_path(self, clock: FrozenClock) -> None:
        env = await _submit(clock)
        uc = CancelSubmissionUseCase(
            FakeUow(), env["fanfics"], env["chapters"], env["moderation"], clock
        )
        await uc(CancelSubmissionCommand(fic_id=env["fic_id"], author_id=1))
        fic = await env["fanfics"].get(FanficId(env["fic_id"]))
        assert fic is not None
        assert fic.status == FicStatus.DRAFT

    async def test_blocked_when_moderator_has_lock(self, clock: FrozenClock) -> None:
        env = await _submit(clock)
        # модератор берёт в работу
        await env["moderation"].pick_next(moderator_id=UserId(99), now=clock.now())
        uc = CancelSubmissionUseCase(
            FakeUow(), env["fanfics"], env["chapters"], env["moderation"], clock
        )
        with pytest.raises(CaseBeingReviewedError):
            await uc(CancelSubmissionCommand(fic_id=env["fic_id"], author_id=1))
