"""Unit-тест SubmitForReviewUseCase."""

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
from app.core.clock import FrozenClock
from app.core.config import get_settings
from app.domain.fanfics.exceptions import EmptyFanficError
from app.domain.fanfics.value_objects import FicStatus, MqKind

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


class TestSubmitForReview:
    async def _env(self, clock: FrozenClock):
        users = FakeUsers()
        users.add(make_user(tg_id=1))
        return {
            "users": users,
            "fanfics": FakeFanfics(),
            "chapters": FakeChapters(),
            "tags": FakeTags(),
            "ref": FakeReference(),
            "versions": FakeVersions(),
            "moderation": FakeModeration(),
            "outbox": FakeOutbox(),
            "clock": clock,
            "settings": get_settings(),
        }

    async def test_first_publish_kind_and_outbox(self, clock: FrozenClock) -> None:
        env = await self._env(clock)
        create = CreateDraftUseCase(
            FakeUow(), env["fanfics"], env["tags"], env["ref"], env["users"], clock
        )
        draft = await create(
            CreateDraftCommand(
                author_id=1,
                title="Title",
                summary="Summary",
                summary_entities=[],
                fandom_id=1,
                age_rating_id=1,
                tag_raws=["tag1"],
            )
        )
        add_ch = AddChapterUseCase(
            FakeUow(), env["fanfics"], env["chapters"], clock, env["settings"]
        )
        await add_ch(
            AddChapterCommand(
                fic_id=draft.fic_id,
                author_id=1,
                title="Ch1",
                text="text",
                entities=[],
            )
        )

        submit = SubmitForReviewUseCase(
            FakeUow(),
            env["fanfics"],
            env["chapters"],
            env["versions"],
            env["moderation"],
            env["outbox"],
            env["users"],
            env["clock"],
            env["settings"],
        )
        result = await submit(SubmitForReviewCommand(fic_id=draft.fic_id, author_id=1))
        assert result.kind == MqKind.FIC_FIRST_PUBLISH
        assert result.version_no == 1

        from app.domain.shared.types import FanficId

        fic_domain = await env["fanfics"].get(FanficId(draft.fic_id))
        assert fic_domain is not None
        assert fic_domain.status == FicStatus.PENDING
        assert any(e[0] == "fanfic.submitted" for e in env["outbox"].events)

    async def test_empty_rejected(self, clock: FrozenClock) -> None:
        env = await self._env(clock)
        create = CreateDraftUseCase(
            FakeUow(), env["fanfics"], env["tags"], env["ref"], env["users"], clock
        )
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
        submit = SubmitForReviewUseCase(
            FakeUow(),
            env["fanfics"],
            env["chapters"],
            env["versions"],
            env["moderation"],
            env["outbox"],
            env["users"],
            env["clock"],
            env["settings"],
        )
        with pytest.raises(EmptyFanficError):
            await submit(SubmitForReviewCommand(fic_id=draft.fic_id, author_id=1))
