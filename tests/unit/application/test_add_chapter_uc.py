"""Unit-тесты AddChapterUseCase."""

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
from app.core.clock import FrozenClock
from app.core.config import Settings, get_settings
from app.domain.fanfics.exceptions import (
    ChapterCharsLimitExceededError,
    FanficChapterLimitExceededError,
)

from ._fakes import (
    FakeChapters,
    FakeFanfics,
    FakeReference,
    FakeTags,
    FakeUow,
    FakeUsers,
    make_user,
)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def settings() -> Settings:
    return get_settings()


class TestAddChapter:
    async def _make_fic(
        self, clock: FrozenClock
    ) -> tuple[int, FakeUow, FakeFanfics, FakeChapters, FakeUsers, Settings]:
        users = FakeUsers()
        users.add(make_user(tg_id=1))
        fanfics = FakeFanfics()
        chapters = FakeChapters()
        tags = FakeTags()
        ref = FakeReference()
        uow = FakeUow()
        create = CreateDraftUseCase(uow, fanfics, tags, ref, users, clock)
        result = await create(
            CreateDraftCommand(
                author_id=1,
                title="Title",
                summary="Summary",
                summary_entities=[],
                fandom_id=1,
                age_rating_id=1,
                tag_raws=[],
            )
        )
        return result.fic_id, uow, fanfics, chapters, users, get_settings()

    async def test_happy_path(self, clock: FrozenClock) -> None:
        fic_id, uow, fanfics, chapters, users, settings = await self._make_fic(clock)
        uc = AddChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        res = await uc(
            AddChapterCommand(
                fic_id=fic_id,
                author_id=1,
                title="Глава 1",
                text="hello world",
                entities=[],
            )
        )
        assert res.number == 1
        assert res.chapter_id > 0

    async def test_too_long_text_rejected(self, clock: FrozenClock) -> None:
        fic_id, _, fanfics, chapters, _, settings = await self._make_fic(clock)
        uc = AddChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        long_text = "a" * (settings.max_chapter_chars + 1)
        with pytest.raises(ChapterCharsLimitExceededError):
            await uc(
                AddChapterCommand(
                    fic_id=fic_id,
                    author_id=1,
                    title="X",
                    text=long_text,
                    entities=[],
                )
            )

    async def test_chapter_limit(self, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch) -> None:
        fic_id, _, fanfics, chapters, _, settings = await self._make_fic(clock)

        # подменим settings.max_chapters_per_fic → 2 для скорости

        class S:
            max_chapters_per_fic = 2
            max_chapter_chars = settings.max_chapter_chars

        uc = AddChapterUseCase(FakeUow(), fanfics, chapters, clock, S())  # type: ignore[arg-type]
        await uc(AddChapterCommand(fic_id=fic_id, author_id=1, title="A", text="x", entities=[]))
        await uc(AddChapterCommand(fic_id=fic_id, author_id=1, title="B", text="y", entities=[]))
        with pytest.raises(FanficChapterLimitExceededError):
            await uc(
                AddChapterCommand(fic_id=fic_id, author_id=1, title="C", text="z", entities=[])
            )
