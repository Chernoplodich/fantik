"""Unit-тесты ReviseAfterRejectionUseCase и DeleteDraftChapterUseCase."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.fanfics.add_chapter import AddChapterCommand, AddChapterUseCase
from app.application.fanfics.create_draft import (
    CreateDraftCommand,
    CreateDraftUseCase,
)
from app.application.fanfics.delete_draft_chapter import (
    DeleteDraftChapterCommand,
    DeleteDraftChapterUseCase,
)
from app.application.fanfics.revise_after_rejection import (
    ReviseAfterRejectionCommand,
    ReviseAfterRejectionUseCase,
)
from app.core.clock import FrozenClock
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import (
    ForbiddenActionError,
    WrongStatusError,
)
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, FanficId

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


async def _seed(
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
    r = await create(
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
    add = AddChapterUseCase(FakeUow(), fanfics, chapters, clock, settings)
    ch = await add(
        AddChapterCommand(fic_id=r.fic_id, author_id=author_id, title="G", text="t", entities=[])
    )
    return r.fic_id, ch.chapter_id, fanfics, chapters


class TestReviseAfterRejection:
    async def test_happy_path(self, clock: FrozenClock, settings: Settings) -> None:
        fic_id, _, fanfics, _ = await _seed(clock, settings)
        fic = await fanfics.get(FanficId(fic_id))
        assert fic is not None
        fic.status = FicStatus.REJECTED
        await fanfics.save(fic)

        uc = ReviseAfterRejectionUseCase(FakeUow(), fanfics, clock)
        await uc(ReviseAfterRejectionCommand(fic_id=fic_id, author_id=1))

        fic_after = await fanfics.get(FanficId(fic_id))
        assert fic_after is not None
        assert fic_after.status == FicStatus.REVISING

    async def test_cannot_revise_draft(self, clock: FrozenClock, settings: Settings) -> None:
        fic_id, _, fanfics, _ = await _seed(clock, settings)
        uc = ReviseAfterRejectionUseCase(FakeUow(), fanfics, clock)
        with pytest.raises(WrongStatusError):
            await uc(ReviseAfterRejectionCommand(fic_id=fic_id, author_id=1))

    async def test_approved_can_start_revising(
        self, clock: FrozenClock, settings: Settings
    ) -> None:
        """approved → revising: автор нажал «🔄 Внести правку» на опубликованном фике."""
        fic_id, _, fanfics, _ = await _seed(clock, settings)
        fic = await fanfics.get(FanficId(fic_id))
        assert fic is not None
        fic.status = FicStatus.APPROVED
        await fanfics.save(fic)

        uc = ReviseAfterRejectionUseCase(FakeUow(), fanfics, clock)
        await uc(ReviseAfterRejectionCommand(fic_id=fic_id, author_id=1))

        fic_after = await fanfics.get(FanficId(fic_id))
        assert fic_after is not None
        assert fic_after.status == FicStatus.REVISING

    async def test_wrong_author_forbidden(self, clock: FrozenClock, settings: Settings) -> None:
        fic_id, _, fanfics, _ = await _seed(clock, settings)
        fic = await fanfics.get(FanficId(fic_id))
        assert fic is not None
        fic.status = FicStatus.REJECTED
        await fanfics.save(fic)
        uc = ReviseAfterRejectionUseCase(FakeUow(), fanfics, clock)
        with pytest.raises(ForbiddenActionError):
            await uc(ReviseAfterRejectionCommand(fic_id=fic_id, author_id=777))


class TestDeleteDraftChapter:
    async def test_happy_path(self, clock: FrozenClock, settings: Settings) -> None:
        fic_id, ch_id, fanfics, chapters = await _seed(clock, settings)
        uc = DeleteDraftChapterUseCase(FakeUow(), fanfics, chapters)
        await uc(DeleteDraftChapterCommand(chapter_id=ch_id, author_id=1))

        assert await chapters.get(ChapterId(ch_id)) is None
        fic = await fanfics.get(FanficId(fic_id))
        assert fic is not None
        assert fic.chapters_count == 0

    async def test_cannot_delete_approved_chapter(
        self, clock: FrozenClock, settings: Settings
    ) -> None:
        _, ch_id, fanfics, chapters = await _seed(clock, settings)
        ch = await chapters.get(ChapterId(ch_id))
        assert ch is not None
        ch.status = FicStatus.APPROVED
        await chapters.save(ch)

        uc = DeleteDraftChapterUseCase(FakeUow(), fanfics, chapters)
        with pytest.raises(WrongStatusError):
            await uc(DeleteDraftChapterCommand(chapter_id=ch_id, author_id=1))

    async def test_wrong_author_forbidden(self, clock: FrozenClock, settings: Settings) -> None:
        _, ch_id, fanfics, chapters = await _seed(clock, settings)
        uc = DeleteDraftChapterUseCase(FakeUow(), fanfics, chapters)
        with pytest.raises(ForbiddenActionError):
            await uc(DeleteDraftChapterCommand(chapter_id=ch_id, author_id=777))

    async def test_missing_chapter(self, clock: FrozenClock, settings: Settings) -> None:
        _, _, fanfics, chapters = await _seed(clock, settings)
        uc = DeleteDraftChapterUseCase(FakeUow(), fanfics, chapters)
        with pytest.raises(NotFoundError):
            await uc(DeleteDraftChapterCommand(chapter_id=99999, author_id=1))
