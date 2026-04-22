"""Unit-тесты Approve/Reject use cases."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.fanfics.add_chapter import (
    AddChapterCommand,
    AddChapterUseCase,
)
from app.application.fanfics.create_draft import (
    CreateDraftCommand,
    CreateDraftUseCase,
)
from app.application.fanfics.submit_for_review import (
    SubmitForReviewCommand,
    SubmitForReviewUseCase,
)
from app.application.moderation.approve import ApproveCommand, ApproveUseCase
from app.application.moderation.reject import RejectCommand, RejectUseCase
from app.core.clock import FrozenClock
from app.core.config import get_settings
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FanficId, ModerationReasonId, UserId

from ._fakes import (
    FakeAudit,
    FakeChapters,
    FakeFanfics,
    FakeModeration,
    FakeNotifier,
    FakeOutbox,
    FakeReasons,
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


async def _submit_fic(clock: FrozenClock) -> dict:
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
        AddChapterCommand(
            fic_id=draft.fic_id, author_id=1, title="Ch1", text="text", entities=[]
        )
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
    submit_res = await submit(SubmitForReviewCommand(fic_id=draft.fic_id, author_id=1))
    return {
        "fic_id": draft.fic_id,
        "case_id": submit_res.case_id,
        "fanfics": fanfics,
        "chapters": chapters,
        "moderation": moderation,
        "versions": versions,
        "outbox": outbox,
    }


class TestApproveReject:
    async def test_approve_writes_outbox_and_notifier(self, clock: FrozenClock) -> None:
        env = await _submit_fic(clock)
        # модератор берёт в работу
        case = await env["moderation"].pick_next(moderator_id=UserId(99), now=clock.now())
        assert case is not None and case.id == env["case_id"]

        notifier = FakeNotifier()
        audit = FakeAudit()
        uc = ApproveUseCase(
            FakeUow(),
            env["moderation"],
            env["fanfics"],
            env["chapters"],
            env["versions"],
            env["outbox"],
            audit,
            notifier,
            clock,
        )
        await uc(ApproveCommand(case_id=env["case_id"], moderator_id=99))

        fic = await env["fanfics"].get(FanficId(env["fic_id"]))
        assert fic.status == FicStatus.APPROVED
        assert fic.first_published_at is not None
        assert any(e[0] == "fanfic.approved" for e in env["outbox"].events)
        assert any(entry["action"] == "fic.approve" for entry in audit.entries)
        assert len(notifier.approved) == 1

    async def test_reject_with_reasons(self, clock: FrozenClock) -> None:
        env = await _submit_fic(clock)
        await env["moderation"].pick_next(moderator_id=UserId(99), now=clock.now())
        reasons = FakeReasons()
        notifier = FakeNotifier()
        audit = FakeAudit()
        uc = RejectUseCase(
            FakeUow(),
            env["moderation"],
            reasons,
            env["fanfics"],
            env["chapters"],
            env["outbox"],
            audit,
            notifier,
            clock,
        )
        await uc(
            RejectCommand(
                case_id=env["case_id"],
                moderator_id=99,
                reason_ids=[1, 2],
                comment="низкое качество",
                comment_entities=[],
            )
        )

        fic = await env["fanfics"].get(FanficId(env["fic_id"]))
        assert fic.status == FicStatus.REJECTED
        assert any(e[0] == "fanfic.rejected" for e in env["outbox"].events)
        assert len(notifier.rejected) == 1
        (_, _, _, picked_reasons, comment) = notifier.rejected[0]
        assert len(picked_reasons) == 2
        assert comment == "низкое качество"

    async def test_cannot_approve_own(self, clock: FrozenClock) -> None:
        from app.domain.moderation.exceptions import CannotModerateOwnWorkError

        env = await _submit_fic(clock)
        notifier = FakeNotifier()
        audit = FakeAudit()
        uc = ApproveUseCase(
            FakeUow(),
            env["moderation"],
            env["fanfics"],
            env["chapters"],
            env["versions"],
            env["outbox"],
            audit,
            notifier,
            clock,
        )
        # moderator_id == submitted_by (1) — нельзя
        with pytest.raises(CannotModerateOwnWorkError):
            await uc(ApproveCommand(case_id=env["case_id"], moderator_id=1))
