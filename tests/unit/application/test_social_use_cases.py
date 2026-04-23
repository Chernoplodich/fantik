"""Unit-тесты social use cases (подписки, жалобы, fanout-раздатчик)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.reports.create_report import (
    CreateReportCommand,
    CreateReportUseCase,
)
from app.application.reports.handle_report import (
    HandleReportCommand,
    HandleReportUseCase,
)
from app.application.reports.ports import IReportRepository, ReportListItem
from app.application.subscriptions.notify_subscribers import (
    NOTIF_KIND_NEW_CHAPTER,
    NotifySubscribersCommand,
    NotifySubscribersUseCase,
)
from app.application.subscriptions.ports import (
    DeliverOneCommand,
    INotificationQueue,
    INotificationRepository,
    ISubscriptionRepository,
)
from app.application.subscriptions.subscribe import (
    SubscribeCommand,
    SubscribeUseCase,
)
from app.application.subscriptions.unsubscribe import (
    UnsubscribeCommand,
    UnsubscribeUseCase,
)
from app.core.clock import FrozenClock
from app.domain.fanfics.entities import Fanfic
from app.domain.fanfics.value_objects import (
    FicStatus,
    FanficTitle,
    Summary,
)
from app.domain.reports.entities import Report
from app.domain.reports.exceptions import SelfReportError
from app.domain.reports.value_objects import ReportStatus, ReportTarget
from app.domain.shared.types import (
    FandomId,
    FanficId,
    NotificationId,
    ReportId,
    UserId,
)
from app.domain.subscriptions.events import UserSubscribedToAuthor
from app.domain.subscriptions.exceptions import SelfSubscribeError
from tests.unit.application._fakes import (
    FakeAudit,
    FakeChapters,
    FakeFanfics,
    FakeOutbox,
    FakeUow,
)

pytestmark = pytest.mark.asyncio


# ---------- fakes ----------


class FakeSubs(ISubscriptionRepository):
    def __init__(self) -> None:
        self._data: set[tuple[int, int]] = set()

    async def add_if_absent(
        self, *, subscriber_id: UserId, author_id: UserId, now: datetime
    ) -> bool:
        key = (int(subscriber_id), int(author_id))
        if key in self._data:
            return False
        self._data.add(key)
        return True

    async def remove(self, *, subscriber_id: UserId, author_id: UserId) -> bool:
        key = (int(subscriber_id), int(author_id))
        if key not in self._data:
            return False
        self._data.remove(key)
        return True

    async def exists(self, *, subscriber_id: UserId, author_id: UserId) -> bool:
        return (int(subscriber_id), int(author_id)) in self._data

    async def iter_subscriber_ids(
        self, *, author_id: UserId, chunk_size: int = 500
    ) -> AsyncIterator[list[UserId]]:
        subs = sorted(s for s, a in self._data if a == int(author_id))
        i = 0
        while i < len(subs):
            yield [UserId(s) for s in subs[i : i + chunk_size]]
            i += chunk_size


class FakeNotifications(INotificationRepository):
    def __init__(self) -> None:
        self.created: list[tuple[int, str, dict[str, Any]]] = []
        self.sent: list[int] = []
        self._seq = 0

    async def create(
        self,
        *,
        user_id: UserId,
        kind: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> NotificationId:
        self._seq += 1
        self.created.append((int(user_id), kind, dict(payload)))
        return NotificationId(self._seq)

    async def create_many(
        self,
        *,
        user_ids: list[UserId],
        kind: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> list[NotificationId]:
        ids: list[NotificationId] = []
        for uid in user_ids:
            self._seq += 1
            self.created.append((int(uid), kind, dict(payload)))
            ids.append(NotificationId(self._seq))
        return ids

    async def mark_sent(self, *, notification_id: NotificationId, now: datetime) -> None:
        self.sent.append(int(notification_id))


class FakeNotifQueue(INotificationQueue):
    def __init__(self) -> None:
        self.fanout_new_chapter: list[tuple[int, int, int]] = []
        self.fanout_new_work: list[tuple[int, int]] = []
        self.delivered: list[DeliverOneCommand] = []

    async def enqueue_fanout_new_chapter(
        self, *, author_id: UserId, fic_id: int, chapter_id: int
    ) -> None:
        self.fanout_new_chapter.append((int(author_id), fic_id, chapter_id))

    async def enqueue_fanout_new_work(self, *, author_id: UserId, fic_id: int) -> None:
        self.fanout_new_work.append((int(author_id), fic_id))

    async def enqueue_deliver_one(self, cmd: DeliverOneCommand) -> None:
        self.delivered.append(cmd)


class FakeReports(IReportRepository):
    def __init__(self) -> None:
        self._by_id: dict[int, Report] = {}
        self._seq = 0

    async def create(
        self,
        *,
        reporter_id: UserId,
        target_type: ReportTarget,
        target_id: int,
        reason_code: str | None,
        text: str | None,
        text_entities: list[dict[str, object]],
        notify_reporter: bool,
        now: datetime,
    ) -> Report:
        self._seq += 1
        r = Report(
            id=ReportId(self._seq),
            reporter_id=reporter_id,
            target_type=target_type,
            target_id=int(target_id),
            reason_code=reason_code,
            text=text,
            text_entities=list(text_entities),
            status=ReportStatus.OPEN,
            notify_reporter=notify_reporter,
            created_at=now,
        )
        self._by_id[int(r.id)] = r
        return r

    async def get(self, report_id: ReportId) -> Report | None:
        return self._by_id.get(int(report_id))

    async def save(self, report: Report) -> None:
        self._by_id[int(report.id)] = report

    async def exists_open_from_reporter(
        self,
        *,
        reporter_id: UserId,
        target_type: ReportTarget,
        target_id: int,
    ) -> ReportId | None:
        for r in self._by_id.values():
            if (
                r.reporter_id == reporter_id
                and r.target_type == target_type
                and int(r.target_id) == int(target_id)
                and r.status == ReportStatus.OPEN
            ):
                return r.id
        return None

    async def list_open(self, *, limit: int, offset: int) -> tuple[list[ReportListItem], int]:
        opens = [r for r in self._by_id.values() if r.status == ReportStatus.OPEN]
        total = len(opens)
        items = [
            ReportListItem(
                id=r.id,
                reporter_id=r.reporter_id,
                target_type=r.target_type,
                target_id=r.target_id,
                reason_code=r.reason_code,
                text_preview=(r.text or "")[:120],
                created_at=r.created_at or datetime.now(UTC),
            )
            for r in opens[offset : offset + limit]
        ]
        return items, total


# ---------- helpers ----------


def _make_fic(
    *,
    fic_id: int = 1,
    author_id: int = 42,
    status: FicStatus = FicStatus.APPROVED,
) -> Fanfic:
    return Fanfic(
        id=FanficId(fic_id),
        author_id=UserId(author_id),
        title=FanficTitle("Работа"),
        summary=Summary("Аннотация"),
        summary_entities=[],
        cover_file_id=None,
        cover_file_unique_id=None,
        fandom_id=FandomId(1),
        age_rating_id=1,
        status=status,
    )


_CLOCK = FrozenClock(at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC))


# ---------- subscribe ----------


async def test_subscribe_twice_yields_single_row_and_one_event() -> None:
    uow = FakeUow()
    subs = FakeSubs()
    fanfics = FakeFanfics()
    await fanfics.save(_make_fic())
    uc = SubscribeUseCase(uow, subs, fanfics, _CLOCK)

    r1 = await uc(SubscribeCommand(subscriber_id=100, fic_id=1))
    r2 = await uc(SubscribeCommand(subscriber_id=100, fic_id=1))

    assert r1.created is True
    assert r2.created is False
    # один раз sub_created → один event
    assert sum(isinstance(e, UserSubscribedToAuthor) for e in uow.events) == 1
    assert await subs.exists(subscriber_id=UserId(100), author_id=UserId(42))


async def test_subscribe_on_self_raises() -> None:
    uow = FakeUow()
    subs = FakeSubs()
    fanfics = FakeFanfics()
    await fanfics.save(_make_fic(author_id=7))
    uc = SubscribeUseCase(uow, subs, fanfics, _CLOCK)

    with pytest.raises(SelfSubscribeError):
        await uc(SubscribeCommand(subscriber_id=7, fic_id=1))


async def test_unsubscribe_idempotent() -> None:
    uow = FakeUow()
    subs = FakeSubs()
    fanfics = FakeFanfics()
    await fanfics.save(_make_fic())
    sub_uc = SubscribeUseCase(uow, subs, fanfics, _CLOCK)
    unsub_uc = UnsubscribeUseCase(uow, subs, fanfics)

    await sub_uc(SubscribeCommand(subscriber_id=5, fic_id=1))
    r1 = await unsub_uc(UnsubscribeCommand(subscriber_id=5, fic_id=1))
    r2 = await unsub_uc(UnsubscribeCommand(subscriber_id=5, fic_id=1))
    assert r1.removed is True
    assert r2.removed is False


# ---------- notify_subscribers ----------


async def test_notify_subscribers_batches_and_queues_deliveries() -> None:
    uow = FakeUow()
    subs = FakeSubs()
    notifs = FakeNotifications()
    fanfics = FakeFanfics()
    chapters = FakeChapters()
    queue = FakeNotifQueue()

    fic = _make_fic(fic_id=10, author_id=42, status=FicStatus.APPROVED)
    await fanfics.save(fic)

    # 250 подписчиков — проверяем чанкинг (100 + 100 + 50).
    author = UserId(42)
    for i in range(250):
        await subs.add_if_absent(subscriber_id=UserId(1000 + i), author_id=author, now=_CLOCK.now())
    # + «подписка на себя» — должна быть отфильтрована use case'ом на всякий случай.
    subs._data.add((int(author), int(author)))  # type: ignore[attr-defined]

    uc = NotifySubscribersUseCase(uow, subs, notifs, fanfics, chapters, queue, _CLOCK)
    result = await uc(
        NotifySubscribersCommand(
            author_id=42, fic_id=10, chapter_id=None, kind="new_work_from_author"
        )
    )

    # Ожидаем ровно 250 доставок (автор-себе-подписка отфильтрована).
    assert result.notifications_created == 250
    assert len(notifs.created) == 250
    assert len(queue.delivered) == 250
    # Подтверждаем, что payload содержит заголовок фика.
    assert queue.delivered[0].payload["fic_title"] == "Работа"


async def test_notify_subscribers_skipped_when_fic_not_approved() -> None:
    uow = FakeUow()
    subs = FakeSubs()
    notifs = FakeNotifications()
    fanfics = FakeFanfics()
    chapters = FakeChapters()
    queue = FakeNotifQueue()

    fic = _make_fic(status=FicStatus.ARCHIVED)
    await fanfics.save(fic)
    # Даже с подписчиком — ничего не шлём.
    await subs.add_if_absent(subscriber_id=UserId(99), author_id=fic.author_id, now=_CLOCK.now())
    uc = NotifySubscribersUseCase(uow, subs, notifs, fanfics, chapters, queue, _CLOCK)
    result = await uc(
        NotifySubscribersCommand(
            author_id=int(fic.author_id),
            fic_id=int(fic.id),
            chapter_id=None,
            kind=NOTIF_KIND_NEW_CHAPTER,
        )
    )
    assert result.notifications_created == 0
    assert queue.delivered == []


# ---------- reports ----------


async def test_create_report_rejects_self_report() -> None:
    uow = FakeUow()
    reports = FakeReports()
    fanfics = FakeFanfics()
    chapters = FakeChapters()
    outbox = FakeOutbox()
    audit = FakeAudit()

    fic = _make_fic(author_id=42)
    await fanfics.save(fic)

    uc = CreateReportUseCase(uow, reports, fanfics, chapters, outbox, audit, _CLOCK)
    with pytest.raises(SelfReportError):
        await uc(
            CreateReportCommand(
                reporter_id=42,  # автор == репортер
                target_type=ReportTarget.FANFIC,
                target_id=1,
                reason_code="SPAM",
                text=None,
            )
        )


async def test_create_report_dedupes_open_from_same_reporter() -> None:
    uow = FakeUow()
    reports = FakeReports()
    fanfics = FakeFanfics()
    chapters = FakeChapters()
    outbox = FakeOutbox()
    audit = FakeAudit()

    fic = _make_fic(author_id=42)
    await fanfics.save(fic)

    uc = CreateReportUseCase(uow, reports, fanfics, chapters, outbox, audit, _CLOCK)
    r1 = await uc(
        CreateReportCommand(
            reporter_id=7,
            target_type=ReportTarget.FANFIC,
            target_id=1,
            reason_code="SPAM",
            text="не хочется видеть",
        )
    )
    r2 = await uc(
        CreateReportCommand(
            reporter_id=7,
            target_type=ReportTarget.FANFIC,
            target_id=1,
            reason_code="NSFW_UNMARKED",
            text="меня задевает",
        )
    )
    assert r1.created is True
    assert r2.created is False
    assert r1.report_id == r2.report_id
    # ровно один outbox-event report.created
    assert sum(1 for ev, _ in outbox.events if ev == "report.created") == 1


async def test_handle_report_action_archives_fanfic_and_emits_outbox() -> None:
    uow = FakeUow()
    reports = FakeReports()
    fanfics = FakeFanfics()
    outbox = FakeOutbox()
    audit = FakeAudit()

    fic = _make_fic(author_id=42, status=FicStatus.APPROVED)
    await fanfics.save(fic)
    report = await reports.create(
        reporter_id=UserId(7),
        target_type=ReportTarget.FANFIC,
        target_id=int(fic.id),
        reason_code="SPAM",
        text="foo",
        text_entities=[],
        notify_reporter=True,
        now=_CLOCK.now(),
    )

    uc = HandleReportUseCase(uow, reports, fanfics, outbox, audit, _CLOCK)
    result = await uc(
        HandleReportCommand(
            report_id=int(report.id),
            moderator_id=99,
            decision="action",
            comment=None,
            action_kind="archive",
        )
    )
    assert result.decision == "action"
    assert result.archived_fic_id == int(fic.id)
    updated = await fanfics.get(fic.id)
    assert updated is not None and updated.status == FicStatus.ARCHIVED

    types = {ev for ev, _ in outbox.events}
    assert "fanfic.archived" in types
    assert "report.handled" in types
