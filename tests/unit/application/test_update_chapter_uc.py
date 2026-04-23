"""Unit-тесты UpdateChapterUseCase — валидация + защита от чужого доступа."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.fanfics.add_chapter import AddChapterCommand, AddChapterUseCase
from app.application.fanfics.create_draft import (
    CreateDraftCommand,
    CreateDraftUseCase,
)
from app.application.fanfics.update_chapter import (
    UpdateChapterCommand,
    UpdateChapterUseCase,
)
from app.core.clock import FrozenClock
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationError
from app.domain.fanfics.exceptions import (
    ChapterCharsLimitExceededError,
    ForbiddenActionError,
)
from app.domain.fanfics.value_objects import CHAPTER_TITLE_MAX

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


async def _seed_fic_with_chapter(
    clock: FrozenClock, settings: Settings, *, author_id: int = 1
) -> tuple[int, int, FakeFanfics, FakeChapters]:
    users = FakeUsers()
    users.add(make_user(tg_id=author_id))
    fanfics = FakeFanfics()
    tags = FakeTags()
    ref = FakeReference()
    chapters = FakeChapters()
    uow = FakeUow()
    create = CreateDraftUseCase(uow, fanfics, tags, ref, users, clock)
    result = await create(
        CreateDraftCommand(
            author_id=author_id,
            title="Фик",
            summary="S",
            summary_entities=[],
            fandom_id=1,
            age_rating_id=1,
            tag_raws=[],
        )
    )
    add_chapter = AddChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
    ch = await add_chapter(
        AddChapterCommand(
            fic_id=result.fic_id,
            author_id=author_id,
            title="Глава 1",
            text="hello",
            entities=[],
        )
    )
    return result.fic_id, ch.chapter_id, fanfics, chapters


class TestUpdateChapter:
    async def test_happy_edit(self, clock: FrozenClock, settings: Settings) -> None:
        _, ch_id, fanfics, chapters = await _seed_fic_with_chapter(clock, settings)
        uc = UpdateChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        await uc(
            UpdateChapterCommand(
                chapter_id=ch_id,
                author_id=1,
                title="Новое название",
                text="Новый текст",
                entities=[],
            )
        )

    async def test_title_too_long_rejected(self, clock: FrozenClock, settings: Settings) -> None:
        _, ch_id, fanfics, chapters = await _seed_fic_with_chapter(clock, settings)
        uc = UpdateChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        with pytest.raises(ValidationError):
            await uc(
                UpdateChapterCommand(
                    chapter_id=ch_id,
                    author_id=1,
                    title="x" * (CHAPTER_TITLE_MAX + 1),
                    text="ok",
                    entities=[],
                )
            )

    async def test_text_too_long_rejected(self, clock: FrozenClock, settings: Settings) -> None:
        _, ch_id, fanfics, chapters = await _seed_fic_with_chapter(clock, settings)
        uc = UpdateChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        with pytest.raises(ChapterCharsLimitExceededError):
            await uc(
                UpdateChapterCommand(
                    chapter_id=ch_id,
                    author_id=1,
                    title="ok",
                    text="x" * (settings.max_chapter_chars + 1),
                    entities=[],
                )
            )

    async def test_forbidden_for_wrong_author(self, clock: FrozenClock, settings: Settings) -> None:
        _, ch_id, fanfics, chapters = await _seed_fic_with_chapter(clock, settings)
        uc = UpdateChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        with pytest.raises(ForbiddenActionError):
            await uc(
                UpdateChapterCommand(
                    chapter_id=ch_id,
                    author_id=999,
                    title="x",
                    text="y",
                    entities=[],
                )
            )

    async def test_missing_chapter_rejected(self, clock: FrozenClock, settings: Settings) -> None:
        _, _, fanfics, chapters = await _seed_fic_with_chapter(clock, settings)
        uc = UpdateChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
        with pytest.raises(NotFoundError):
            await uc(
                UpdateChapterCommand(
                    chapter_id=99999,
                    author_id=1,
                    title="x",
                    text="y",
                    entities=[],
                )
            )
