"""Переиспользуемые фейки для unit-тестов Stage 2 use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Any, Self

from app.application.fanfics.ports import (
    AgeRatingRef,
    FandomRef,
    FanficListItem,
    FanficWithChapters,
    IAuthorNotifier,
    IChapterRepository,
    IFanficRepository,
    IFanficVersionRepository,
    IOutboxRepository,
    IReferenceReader,
    ITagRepository,
    TagRef,
)
from app.application.moderation.ports import (
    IAuditLog,
    IModerationRepository,
    IReasonRepository,
)
from app.application.users.ports import IUserRepository
from app.domain.fanfics.entities import Chapter, Fanfic
from app.domain.fanfics.value_objects import (
    AgeRatingCode,
    FicStatus,
    MqKind,
    TagName,
    TagSlug,
)
from app.domain.moderation.entities import ModerationCase
from app.domain.moderation.value_objects import ReasonCode, RejectionReason
from app.domain.shared.events import DomainEvent
from app.domain.shared.types import (
    AuditLogId,
    ChapterId,
    FandomId,
    FanficId,
    FanficVersionId,
    ModerationCaseId,
    ModerationReasonId,
    OutboxId,
    TagId,
    UserId,
)
from app.domain.users.entities import User
from app.domain.users.value_objects import AuthorNick, Role


@dataclass
class FakeUow:
    events: list[DomainEvent] = field(default_factory=list)
    committed: bool = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None: ...

    def record_events(self, events: list[DomainEvent]) -> None:
        self.events.extend(events)

    def collect_events(self) -> list[DomainEvent]:
        return list(self.events)


class FakeUsers(IUserRepository):
    def __init__(self) -> None:
        self._by_id: dict[UserId, User] = {}

    def add(self, user: User) -> None:
        self._by_id[user.id] = user

    async def get(self, user_id: UserId) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_nick(self, nick_lower: str) -> User | None:
        for u in self._by_id.values():
            if u.author_nick and u.author_nick.lowered == nick_lower:
                return u
        return None

    async def save(self, user: User) -> None:
        self._by_id[user.id] = user

    async def upsert_touch(self, user: User) -> None:
        await self.save(user)

    async def get_role(self, user_id: UserId) -> str | None:
        u = self._by_id.get(user_id)
        return u.role.value if u else None

    async def is_nick_taken(
        self, nick_lower: str, *, except_user_id: UserId | None = None
    ) -> bool:
        for u in self._by_id.values():
            if (
                u.author_nick
                and u.author_nick.lowered == nick_lower
                and u.id != except_user_id
            ):
                return True
        return False


def make_user(*, tg_id: int = 1, role: Role = Role.USER, nick: str = "nick1") -> User:
    user = User.register(
        tg_id=tg_id,
        username=None,
        first_name=None,
        last_name=None,
        language_code="ru",
        utm_code_id=None,
        now=datetime(2026, 4, 21, tzinfo=__import__("datetime").timezone.utc),
    )
    user.pull_events()
    user.author_nick = AuthorNick(nick)
    user.role = role
    return user


class FakeFanfics(IFanficRepository):
    def __init__(self) -> None:
        self._by_id: dict[FanficId, Fanfic] = {}
        self._seq = 0
        self.submitted_today: int = 0

    async def get(self, fic_id: FanficId) -> Fanfic | None:
        return self._by_id.get(fic_id)

    async def get_with_chapters(
        self, fic_id: FanficId
    ) -> FanficWithChapters | None:
        f = self._by_id.get(fic_id)
        if f is None:
            return None
        return FanficWithChapters(fic=f, chapters=[], tags=[])

    async def save(self, fic: Fanfic) -> Fanfic:
        if int(fic.id) == 0:
            self._seq += 1
            fic.id = FanficId(self._seq)
        self._by_id[fic.id] = fic
        return fic

    async def list_by_author_paginated(
        self, *, author_id: UserId, limit: int, offset: int
    ) -> tuple[list[FanficListItem], int]:
        mine = [
            FanficListItem(
                fic_id=f.id,
                title=str(f.title),
                status=f.status,
                chapters_count=f.chapters_count,
                updated_at=f.updated_at,
            )
            for f in self._by_id.values()
            if f.author_id == author_id
        ]
        return mine[offset : offset + limit], len(mine)

    async def count_submitted_today(
        self, *, author_id: UserId, tz: str
    ) -> int:
        return self.submitted_today


class FakeChapters(IChapterRepository):
    def __init__(self) -> None:
        self._by_id: dict[ChapterId, Chapter] = {}
        self._seq = 0

    async def get(self, chapter_id: ChapterId) -> Chapter | None:
        return self._by_id.get(chapter_id)

    async def save(self, chapter: Chapter) -> Chapter:
        if int(chapter.id) == 0:
            self._seq += 1
            chapter.id = ChapterId(self._seq)
        self._by_id[chapter.id] = chapter
        return chapter

    async def list_by_fic(self, fic_id: FanficId) -> list[Chapter]:
        return [c for c in self._by_id.values() if c.fic_id == fic_id]

    async def list_by_fic_and_statuses(
        self, fic_id: FanficId, statuses: list[FicStatus]
    ) -> list[Chapter]:
        return [
            c
            for c in self._by_id.values()
            if c.fic_id == fic_id and c.status in statuses
        ]

    async def delete(self, chapter_id: ChapterId) -> None:
        self._by_id.pop(chapter_id, None)

    async def count_by_fic(self, fic_id: FanficId) -> int:
        return sum(1 for c in self._by_id.values() if c.fic_id == fic_id)

    async def next_number(self, fic_id: FanficId) -> int:
        nums = [int(c.number) for c in self._by_id.values() if c.fic_id == fic_id]
        return (max(nums) if nums else 0) + 1


class FakeTags(ITagRepository):
    def __init__(self) -> None:
        self._by_slug: dict[str, TagRef] = {}
        self._seq = 0

    async def ensure(
        self, *, name: TagName, slug: TagSlug, kind: str
    ) -> tuple[TagRef, bool]:
        existing = self._by_slug.get(str(slug))
        if existing:
            return existing, False
        self._seq += 1
        ref = TagRef(
            id=TagId(self._seq), name=name, slug=slug, kind=kind, approved=False
        )
        self._by_slug[str(slug)] = ref
        return ref, True

    async def list_by_fic(self, fic_id: FanficId) -> list[TagRef]:
        return []

    async def list_by_fic_ids(
        self, fic_ids: list[FanficId]
    ) -> dict[FanficId, list[TagRef]]:
        return {fid: [] for fid in fic_ids}

    async def replace_for_fic(
        self, *, fic_id: FanficId, tag_ids: list[TagId]
    ) -> None:
        return None


class FakeVersions(IFanficVersionRepository):
    def __init__(self) -> None:
        self._by_fic: dict[FanficId, list[tuple[int, FanficVersionId]]] = {}
        self._seq = 0

    async def next_version_no(self, fic_id: FanficId) -> int:
        prev = self._by_fic.get(fic_id, [])
        return (max((v for v, _ in prev), default=0)) + 1

    async def get_latest_id(self, fic_id: FanficId) -> FanficVersionId | None:
        prev = self._by_fic.get(fic_id)
        if not prev:
            return None
        return max(prev, key=lambda t: t[0])[1]

    async def create_snapshot(
        self,
        *,
        fic_id: FanficId,
        version_no: int,
        title: str,
        summary: str,
        summary_entities: list[dict[str, Any]],
        snapshot_chapters: list[dict[str, Any]],
        now: datetime,
    ) -> FanficVersionId:
        self._seq += 1
        vid = FanficVersionId(self._seq)
        self._by_fic.setdefault(fic_id, []).append((version_no, vid))
        return vid


class FakeReference(IReferenceReader):
    def __init__(self) -> None:
        self.fandom = FandomRef(
            id=FandomId(1), slug="hp", name="Harry Potter", category="books"
        )
        self.rating = AgeRatingRef(
            id=1,
            code=AgeRatingCode("PG"),
            name="PG",
            description="",
            min_age=6,
            sort_order=1,
        )

    async def list_fandoms_paginated(
        self, *, limit: int, offset: int, active_only: bool = True
    ) -> tuple[list[FandomRef], int]:
        return [self.fandom], 1

    async def get_fandom(self, fandom_id: FandomId) -> FandomRef | None:
        return self.fandom if fandom_id == self.fandom.id else None

    async def list_age_ratings(self) -> list[AgeRatingRef]:
        return [self.rating]

    async def get_age_rating(self, rating_id: int) -> AgeRatingRef | None:
        return self.rating if rating_id == self.rating.id else None


class FakeOutbox(IOutboxRepository):
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self._seq = 0

    async def append(
        self, *, event_type: str, payload: dict[str, Any], now: datetime
    ) -> OutboxId:
        self.events.append((event_type, payload))
        self._seq += 1
        return OutboxId(self._seq)


class FakeModeration(IModerationRepository):
    def __init__(self) -> None:
        self._by_id: dict[ModerationCaseId, ModerationCase] = {}
        self._seq = 0

    async def create_case(
        self,
        *,
        fic_id: FanficId,
        chapter_id: ChapterId | None,
        kind: MqKind,
        submitted_by: UserId,
        now: datetime,
    ) -> ModerationCase:
        self._seq += 1
        case = ModerationCase(
            id=ModerationCaseId(self._seq),
            fic_id=fic_id,
            chapter_id=chapter_id,
            kind=kind,
            submitted_by=submitted_by,
            submitted_at=now,
        )
        self._by_id[case.id] = case
        return case

    async def get_by_id(
        self, case_id: ModerationCaseId
    ) -> ModerationCase | None:
        return self._by_id.get(case_id)

    async def get_open_by_fic(self, fic_id: FanficId) -> ModerationCase | None:
        for c in self._by_id.values():
            if (
                c.fic_id == fic_id
                and c.decision is None
                and c.cancelled_at is None
            ):
                return c
        return None

    async def pick_next(
        self, *, moderator_id: UserId, now: datetime
    ) -> ModerationCase | None:
        for c in sorted(self._by_id.values(), key=lambda x: x.submitted_at):
            if (
                c.decision is None
                and c.cancelled_at is None
                and c.submitted_by != moderator_id
                and (c.locked_until is None or c.locked_until < now)
            ):
                c.lock(moderator_id=moderator_id, now=now)
                return c
        return None

    async def save_decision_idempotent(self, case: ModerationCase) -> bool:
        existing = self._by_id.get(case.id)
        if existing is None:
            return False
        # копируем состояние
        self._by_id[case.id] = case
        return True

    async def unlock(
        self, *, case_id: ModerationCaseId, moderator_id: UserId
    ) -> bool:
        c = self._by_id.get(case_id)
        if c is None or c.locked_by != moderator_id:
            return False
        c.locked_by = None
        c.locked_until = None
        return True

    async def release_stale_locks(self, *, now: datetime) -> int:
        released = 0
        for c in self._by_id.values():
            if (
                c.decision is None
                and c.cancelled_at is None
                and c.locked_until is not None
                and c.locked_until < now
            ):
                c.locked_by = None
                c.locked_until = None
                released += 1
        return released

    async def mark_cancelled(
        self, *, case_id: ModerationCaseId, now: datetime
    ) -> bool:
        c = self._by_id.get(case_id)
        if c is None or c.decision is not None or c.cancelled_at is not None:
            return False
        c.cancelled_at = now
        c.locked_by = None
        c.locked_until = None
        return True


class FakeReasons(IReasonRepository):
    def __init__(self) -> None:
        self._reasons: list[RejectionReason] = [
            RejectionReason(
                id=ModerationReasonId(1),
                code=ReasonCode.LOW_QUALITY,
                title="Низкое качество",
                description="desc",
                sort_order=10,
                active=True,
            ),
            RejectionReason(
                id=ModerationReasonId(2),
                code=ReasonCode.WRONG_TAGS,
                title="Неверные теги",
                description="desc",
                sort_order=20,
                active=True,
            ),
        ]

    async def list_active(self) -> list[RejectionReason]:
        return list(self._reasons)

    async def get_by_ids(
        self, reason_ids: list[ModerationReasonId]
    ) -> list[RejectionReason]:
        return [r for r in self._reasons if r.id in reason_ids]


class FakeAudit(IAuditLog):
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self._seq = 0

    async def log(
        self,
        *,
        actor_id: UserId | None,
        action: str,
        target_type: str,
        target_id: int,
        payload: dict[str, Any],
        now: datetime,
    ) -> AuditLogId:
        self._seq += 1
        self.entries.append(
            {
                "actor_id": actor_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "payload": payload,
            }
        )
        return AuditLogId(self._seq)


class FakeNotifier(IAuthorNotifier):
    def __init__(self) -> None:
        self.approved: list[tuple[UserId, FanficId, str]] = []
        self.rejected: list[
            tuple[UserId, FanficId, str, list[RejectionReason], str | None]
        ] = []

    async def notify_approved(
        self, *, author_id: UserId, fic_id: FanficId, fic_title: str
    ) -> None:
        self.approved.append((author_id, fic_id, fic_title))

    async def notify_rejected(
        self,
        *,
        author_id: UserId,
        fic_id: FanficId,
        fic_title: str,
        reasons: list[RejectionReason],
        comment: str | None,
        comment_entities: list[dict[str, Any]],
    ) -> None:
        self.rejected.append((author_id, fic_id, fic_title, reasons, comment))

    async def notify_chapter_approved(self, **_: Any) -> None:
        return None

    async def notify_chapter_rejected(self, **_: Any) -> None:
        return None
