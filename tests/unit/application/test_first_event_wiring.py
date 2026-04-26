"""Тесты wiring трекинговых событий first_publish / first_read.

До этого `RecordEventUseCase` существовал, но никто его не вызывал →
в админ-статистике эти метрики были по нулям, хотя approved-фики и
прочтения накапливались. Регрессионная проверка: при approve и read_page
событие пишется ровно один раз на юзера (only_once=True).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.moderation.approve import ApproveCommand, ApproveUseCase
from app.application.tracking.record_event import (
    RecordEventCommand,
    RecordEventUseCase,
)
from app.core.clock import FrozenClock
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, FanficId, UserId
from app.domain.tracking.value_objects import TrackingEventType

from ._fakes import FakeAudit, FakeNotifier, FakeUow
from .test_approve_reject_uc import _submit_fic


# ---------- общие fakes для трекинга ----------


@dataclass
class TrackedRecord:
    user_id: int
    event_type: str
    only_once: bool
    payload: dict[str, Any]


class FakeRecordEventUseCase:
    """Имитатор `RecordEventUseCase`, не лезущий в БД.

    Захватывает все вызовы и эмулирует семантику `only_once` —
    при повторном вызове с теми же (user, type) возвращает False.
    """

    def __init__(self) -> None:
        self.calls: list[TrackedRecord] = []
        self._seen: set[tuple[int, str]] = set()

    async def __call__(self, cmd: RecordEventCommand) -> bool:
        rec = TrackedRecord(
            user_id=int(cmd.user_id),
            event_type=cmd.event_type.value,
            only_once=cmd.only_once,
            payload=dict(cmd.payload),
        )
        self.calls.append(rec)
        key = (rec.user_id, rec.event_type)
        if cmd.only_once and key in self._seen:
            return False
        self._seen.add(key)
        return True


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC))


# ============================================================
# first_publish при approve
# ============================================================


class TestFirstPublishWiring:
    @pytest.mark.asyncio
    async def test_approve_records_first_publish_for_author(self, clock: FrozenClock) -> None:
        env = await _submit_fic(clock)
        # модератор берёт в работу
        await env["moderation"].pick_next(moderator_id=UserId(99), now=clock.now())

        record_event = FakeRecordEventUseCase()
        uc = ApproveUseCase(
            FakeUow(),
            env["moderation"],
            env["fanfics"],
            env["chapters"],
            env["versions"],
            env["outbox"],
            FakeAudit(),
            FakeNotifier(),
            clock,
            record_event=record_event,  # type: ignore[arg-type]
        )

        await uc(ApproveCommand(case_id=env["case_id"], moderator_id=99))

        # ровно один вызов RecordEvent с правильными параметрами
        assert len(record_event.calls) == 1
        rec = record_event.calls[0]
        assert rec.event_type == TrackingEventType.FIRST_PUBLISH.value
        assert rec.only_once is True
        # автор фика — tg_id=1 (см. _submit_fic в test_approve_reject_uc.py)
        assert rec.user_id == 1
        assert rec.payload.get("fic_id") == env["fic_id"]

    @pytest.mark.asyncio
    async def test_approve_without_record_event_dependency_works(self, clock: FrozenClock) -> None:
        """Регрессия: если record_event=None (legacy-вызов без DI),
        approve должен работать без ошибок и не падать."""
        env = await _submit_fic(clock)
        await env["moderation"].pick_next(moderator_id=UserId(99), now=clock.now())

        uc = ApproveUseCase(
            FakeUow(),
            env["moderation"],
            env["fanfics"],
            env["chapters"],
            env["versions"],
            env["outbox"],
            FakeAudit(),
            FakeNotifier(),
            clock,
            # record_event не передаётся
        )
        await uc(ApproveCommand(case_id=env["case_id"], moderator_id=99))

        fic = await env["fanfics"].get(FanficId(env["fic_id"]))
        assert fic.status == FicStatus.APPROVED


# ============================================================
# first_read при read_page (минимальные fakes)
# ============================================================


class TestFirstReadWiring:
    @pytest.mark.asyncio
    async def test_first_page_of_other_authors_chapter_records_event(
        self, clock: FrozenClock
    ) -> None:
        from app.application.reading.read_page import ReadPageCommand, ReadPageUseCase
        from app.domain.fanfics.entities import Chapter, Fanfic
        from app.domain.fanfics.value_objects import (
            ChapterTitle,
            FanficTitle,
            Summary,
        )
        from app.domain.shared.types import FandomId

        # Approved фик автора 100, читатель 200.
        fic = Fanfic(
            id=FanficId(1),
            author_id=UserId(100),
            title=FanficTitle("Test fic"),
            summary=Summary("a" * 30),
            summary_entities=[],
            cover_file_id=None,
            cover_file_unique_id=None,
            fandom_id=FandomId(1),
            age_rating_id=1,
            status=FicStatus.APPROVED,
            current_version_id=None,
            chapters_count=1,
            chars_count=200,
            first_published_at=clock.now(),
            last_edit_at=clock.now(),
            archived_at=None,
            created_at=clock.now(),
            updated_at=clock.now(),
        )
        # Длинный текст, чтобы пагинатор сделал >= 2 страниц.
        long_text = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 200).strip()
        chapter = Chapter(
            id=ChapterId(10),
            fic_id=FanficId(1),
            number=1,
            title=ChapterTitle("ch1"),
            text=long_text,
            entities=[],
            chars_count=len(long_text),
            status=FicStatus.APPROVED,
            first_approved_at=clock.now(),
            created_at=clock.now(),
            updated_at=clock.now(),
        )

        record_event = FakeRecordEventUseCase()
        uc = ReadPageUseCase(
            fanfics=_FakeFics(fic),  # type: ignore[arg-type]
            chapters=_FakeChs(chapter),  # type: ignore[arg-type]
            pages_repo=_FakePagesRepo(),  # type: ignore[arg-type]
            page_cache=_FakeCacheRepo(),  # type: ignore[arg-type]
            bookmarks=_FakeFlagRepo(),  # type: ignore[arg-type]
            likes=_FakeFlagRepo(),  # type: ignore[arg-type]
            reads_completed=_FakeReadsRepo(),  # type: ignore[arg-type]
            record_event=record_event,  # type: ignore[arg-type]
        )

        # читатель 200 открывает первую страницу
        await uc(ReadPageCommand(user_id=200, fic_id=1, chapter_id=10, page_no=1))

        assert len(record_event.calls) == 1
        rec = record_event.calls[0]
        assert rec.event_type == TrackingEventType.FIRST_READ.value
        assert rec.user_id == 200
        assert rec.only_once is True

        # вторая страница: события не должно быть (избегаем DB-хит на каждый клик)
        await uc(ReadPageCommand(user_id=200, fic_id=1, chapter_id=10, page_no=2))
        assert len(record_event.calls) == 1

    @pytest.mark.asyncio
    async def test_author_reading_own_fic_does_not_record(self, clock: FrozenClock) -> None:
        from app.application.reading.read_page import ReadPageCommand, ReadPageUseCase
        from app.domain.fanfics.entities import Chapter, Fanfic
        from app.domain.fanfics.value_objects import (
            ChapterTitle,
            FanficTitle,
            Summary,
        )
        from app.domain.shared.types import FandomId

        fic = Fanfic(
            id=FanficId(1),
            author_id=UserId(100),
            title=FanficTitle("Test fic"),
            summary=Summary("a" * 30),
            summary_entities=[],
            cover_file_id=None,
            cover_file_unique_id=None,
            fandom_id=FandomId(1),
            age_rating_id=1,
            status=FicStatus.APPROVED,
            current_version_id=None,
            chapters_count=1,
            chars_count=120,
            first_published_at=clock.now(),
            last_edit_at=clock.now(),
            archived_at=None,
            created_at=clock.now(),
            updated_at=clock.now(),
        )
        chapter = Chapter(
            id=ChapterId(10),
            fic_id=FanficId(1),
            number=1,
            title=ChapterTitle("ch1"),
            text="Lorem ipsum " * 10,
            entities=[],
            chars_count=120,
            status=FicStatus.APPROVED,
            first_approved_at=clock.now(),
            created_at=clock.now(),
            updated_at=clock.now(),
        )

        record_event = FakeRecordEventUseCase()
        uc = ReadPageUseCase(
            fanfics=_FakeFics(fic),  # type: ignore[arg-type]
            chapters=_FakeChs(chapter),  # type: ignore[arg-type]
            pages_repo=_FakePagesRepo(),  # type: ignore[arg-type]
            page_cache=_FakeCacheRepo(),  # type: ignore[arg-type]
            bookmarks=_FakeFlagRepo(),  # type: ignore[arg-type]
            likes=_FakeFlagRepo(),  # type: ignore[arg-type]
            reads_completed=_FakeReadsRepo(),  # type: ignore[arg-type]
            record_event=record_event,  # type: ignore[arg-type]
        )

        # автор 100 читает свой же фик
        await uc(ReadPageCommand(user_id=100, fic_id=1, chapter_id=10, page_no=1))

        # автор != читатель → событие не должно записаться
        assert len(record_event.calls) == 0


# ---------- минимальные fakes для ReadPageUseCase ----------


@dataclass
class _FakeFics:
    fic: Any

    async def get(self, fic_id: FanficId) -> Any:  # noqa: ARG002
        return self.fic


@dataclass
class _FakeChs:
    chapter: Any

    async def get(self, ch_id: ChapterId) -> Any:  # noqa: ARG002
        return self.chapter

    async def list_by_fic(self, fic_id: FanficId) -> list[Any]:  # noqa: ARG002
        return [self.chapter]


@dataclass
class _FakePagesRepo:
    async def count_by_chapter(self, chapter_id: ChapterId) -> int:  # noqa: ARG002
        return 0  # форсирует lazy-пагинацию

    async def get(self, chapter_id: ChapterId, page_no: int) -> Any:  # noqa: ARG002
        return None


@dataclass
class _FakeCacheRepo:
    items: dict[tuple[int, int], Any] = field(default_factory=dict)

    async def get(self, chapter_id: ChapterId, page_no: int) -> Any:  # noqa: ARG002
        return None

    async def set(self, chapter_id: ChapterId, page_no: int, value: Any) -> None:
        self.items[(int(chapter_id), int(page_no))] = value


@dataclass
class _FakeFlagRepo:
    flagged: set[tuple[int, int]] = field(default_factory=set)

    async def exists(self, user_id: UserId, fic_id: FanficId) -> bool:
        return (int(user_id), int(fic_id)) in self.flagged


@dataclass
class _FakeReadsRepo:
    completed: set[tuple[int, int]] = field(default_factory=set)

    async def exists(self, user_id: UserId, chapter_id: ChapterId) -> bool:
        return (int(user_id), int(chapter_id)) in self.completed
