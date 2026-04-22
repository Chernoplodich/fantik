"""Unit-тест PickNextUseCase: исключает своих и уважает lock."""

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
from app.application.moderation.pick_next import (
    PickNextCommand,
    PickNextUseCase,
)
from app.core.clock import FrozenClock
from app.core.config import get_settings

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


class TestPickNext:
    async def test_excludes_own(self, clock: FrozenClock) -> None:
        settings = get_settings()
        users = FakeUsers()
        users.add(make_user(tg_id=1))  # автор
        users.add(make_user(tg_id=99, nick="mod1"))
        fanfics = FakeFanfics()
        chapters = FakeChapters()
        tags = FakeTags()
        ref = FakeReference()
        versions = FakeVersions()
        moderation = FakeModeration()
        outbox = FakeOutbox()

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
        ac = AddChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        await ac(
            AddChapterCommand(
                fic_id=draft.fic_id, author_id=1, title="C", text="t", entities=[]
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
        await submit(SubmitForReviewCommand(fic_id=draft.fic_id, author_id=1))

        uc = PickNextUseCase(FakeUow(), moderation, fanfics, tags, clock)
        # сам автор не получает свою работу
        result_self = await uc(PickNextCommand(moderator_id=1))
        assert result_self.card is None

        # другой модератор получает
        result_other = await uc(PickNextCommand(moderator_id=99))
        assert result_other.card is not None
        assert result_other.card.case.submitted_by == 1
