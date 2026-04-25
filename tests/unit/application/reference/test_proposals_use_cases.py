"""Use cases для заявок на новый фандом."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.reference.fandoms_crud import (
    CreateFandomCommand,
    CreateFandomUseCase,
)
from app.application.reference.ports import (
    FandomAdminRow,
    FandomProposalRow,
    IFandomAdminRepository,
    IFandomProposalNotifier,
    IFandomProposalRepository,
)
from app.application.reference.proposals import (
    ApproveFandomProposalCommand,
    ApproveFandomProposalUseCase,
    ListPendingFandomProposalsUseCase,
    RejectFandomProposalCommand,
    RejectFandomProposalUseCase,
    SubmitFandomProposalCommand,
    SubmitFandomProposalUseCase,
)
from app.core.clock import FrozenClock
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domain.reference.entities import FandomProposal as ProposalEntity
from app.domain.reference.value_objects import FandomProposalStatus, ProposalId
from app.domain.shared.types import FandomId, UserId

from .._fakes import FakeAudit, FakeUow


# ---------- fakes ----------


class FakeProposalRepo(IFandomProposalRepository):
    def __init__(self) -> None:
        self._items: dict[int, ProposalEntity] = {}
        self._seq = 0
        self.fail_create_with_conflict = False

    async def create(
        self,
        *,
        requested_by: UserId,
        name: str,
        category_hint: str,
        comment: str | None,
        now: datetime,
    ) -> ProposalEntity:
        if self.fail_create_with_conflict:
            raise ConflictError("dup")
        # Ручной анти-дубль для теста уникальности.
        for ex in self._items.values():
            if (
                ex.requested_by == requested_by
                and ex.name.lower() == name.lower()
                and ex.status is FandomProposalStatus.PENDING
            ):
                raise ConflictError("dup")
        self._seq += 1
        p = ProposalEntity(
            id=ProposalId(self._seq),
            requested_by=requested_by,
            name=name,
            category_hint=category_hint,
            comment=comment,
            status=FandomProposalStatus.PENDING,
            created_at=now,
        )
        self._items[self._seq] = p
        return p

    async def get(self, proposal_id: ProposalId) -> ProposalEntity | None:
        return self._items.get(int(proposal_id))

    async def save(self, proposal: ProposalEntity) -> None:
        # in-place update — entity мутабельна.
        self._items[int(proposal.id)] = proposal

    async def list_pending(self, *, limit: int = 50) -> list[FandomProposalRow]:
        rows = [
            self._to_row(p)
            for p in self._items.values()
            if p.status is FandomProposalStatus.PENDING
        ]
        return rows[:limit]

    async def list_recent(
        self, *, status: str | None = None, limit: int = 50
    ) -> list[FandomProposalRow]:
        rows = [self._to_row(p) for p in self._items.values()]
        if status is not None:
            rows = [r for r in rows if r.status == status]
        return rows[:limit]

    @staticmethod
    def _to_row(p: ProposalEntity) -> FandomProposalRow:
        return FandomProposalRow(
            id=p.id,
            name=p.name,
            category_hint=p.category_hint,
            comment=p.comment,
            requested_by=p.requested_by,
            status=p.status.value,
            reviewed_by=p.reviewed_by,
            reviewed_at=p.reviewed_at,
            decision_comment=p.decision_comment,
            created_fandom_id=p.created_fandom_id,
            created_at=p.created_at or datetime.now(tz=UTC),
        )


class FakeFandomAdminRepo(IFandomAdminRepository):
    def __init__(self) -> None:
        self._by_id: dict[int, FandomAdminRow] = {}
        self._seq = 0

    async def list_all(self, *, active_only: bool = False) -> list[FandomAdminRow]:
        rows = list(self._by_id.values())
        if active_only:
            rows = [r for r in rows if r.active]
        return rows

    async def get(self, fandom_id: FandomId) -> FandomAdminRow | None:
        return self._by_id.get(int(fandom_id))

    async def create(
        self,
        *,
        slug: str,
        name: str,
        category: str,
        aliases: list[str],
    ) -> FandomAdminRow:
        for r in self._by_id.values():
            if r.slug == slug:
                raise ConflictError(f"slug «{slug}» exists")
        self._seq += 1
        row = FandomAdminRow(
            id=FandomId(self._seq),
            slug=slug,
            name=name,
            category=category,
            aliases=list(aliases),
            active=True,
        )
        self._by_id[self._seq] = row
        return row

    async def update(self, **kwargs: Any) -> FandomAdminRow:
        raise NotImplementedError


class FakeNotifier(IFandomProposalNotifier):
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def notify_submitted(self, *, requested_by: UserId, name: str) -> None:
        self.events.append(("submitted", {"to": int(requested_by), "name": name}))

    async def notify_approved(
        self, *, requested_by: UserId, name: str, fandom_id: FandomId
    ) -> None:
        self.events.append(
            ("approved", {"to": int(requested_by), "name": name, "fid": int(fandom_id)})
        )

    async def notify_rejected(self, *, requested_by: UserId, name: str, reason: str | None) -> None:
        self.events.append(("rejected", {"to": int(requested_by), "name": name, "reason": reason}))


# ---------- fixtures ----------


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC))


# ---------- Submit ----------


class TestSubmit:
    @pytest.mark.asyncio
    async def test_happy_path_creates_pending(self, clock: FrozenClock) -> None:
        repo = FakeProposalRepo()
        notif = FakeNotifier()
        audit = FakeAudit()
        uc = SubmitFandomProposalUseCase(FakeUow(), repo, notif, audit, clock)

        result = await uc(
            SubmitFandomProposalCommand(
                requested_by=42,
                name="Тестовый фандом",
                category_hint="anime",
            )
        )

        assert result.created is True
        assert int(result.proposal_id) == 1
        assert notif.events == [("submitted", {"to": 42, "name": "Тестовый фандом"})]
        assert any(e["action"] == "fandom_proposal.submit" for e in audit.entries)

    @pytest.mark.asyncio
    async def test_duplicate_returns_created_false(self, clock: FrozenClock) -> None:
        repo = FakeProposalRepo()
        notif = FakeNotifier()
        audit = FakeAudit()
        uc = SubmitFandomProposalUseCase(FakeUow(), repo, notif, audit, clock)

        cmd = SubmitFandomProposalCommand(requested_by=42, name="X", category_hint="anime")
        first = await uc(cmd)
        assert first.created is True

        second = await uc(cmd)
        assert second.created is False
        # Уведомление об уже существующей заявке тоже не шлём.
        assert len(notif.events) == 1

    @pytest.mark.asyncio
    async def test_invalid_category_raises(self, clock: FrozenClock) -> None:
        repo = FakeProposalRepo()
        uc = SubmitFandomProposalUseCase(FakeUow(), repo, FakeNotifier(), FakeAudit(), clock)
        with pytest.raises(ValidationError):
            await uc(
                SubmitFandomProposalCommand(requested_by=42, name="X", category_hint="planets")
            )

    @pytest.mark.asyncio
    async def test_empty_name_raises(self, clock: FrozenClock) -> None:
        repo = FakeProposalRepo()
        uc = SubmitFandomProposalUseCase(FakeUow(), repo, FakeNotifier(), FakeAudit(), clock)
        with pytest.raises(ValidationError):
            await uc(
                SubmitFandomProposalCommand(requested_by=42, name="   ", category_hint="anime")
            )


# ---------- Approve ----------


class TestApprove:
    @pytest.mark.asyncio
    async def test_approve_creates_fandom_and_marks_proposal(self, clock: FrozenClock) -> None:
        proposals_repo = FakeProposalRepo()
        # Создаём заявку напрямую (без notifier).
        await proposals_repo.create(
            requested_by=UserId(42),
            name="Тестовый фандом",
            category_hint="anime",
            comment=None,
            now=clock.now(),
        )

        fandom_repo = FakeFandomAdminRepo()
        create_uc = CreateFandomUseCase(FakeUow(), fandom_repo, FakeAudit(), clock)
        notif = FakeNotifier()
        audit = FakeAudit()
        uc = ApproveFandomProposalUseCase(FakeUow(), proposals_repo, create_uc, notif, audit, clock)

        result = await uc(ApproveFandomProposalCommand(actor_id=7, proposal_id=1))

        assert int(result.fandom_id) == 1
        # proposal помечена approved
        p = await proposals_repo.get(ProposalId(1))
        assert p is not None and p.status is FandomProposalStatus.APPROVED
        assert p.created_fandom_id == FandomId(1)
        # уведомление автору
        assert notif.events == [("approved", {"to": 42, "name": "Тестовый фандом", "fid": 1})]
        # audit
        assert any(e["action"] == "fandom_proposal.approve" for e in audit.entries)

    @pytest.mark.asyncio
    async def test_approve_unknown_raises_not_found(self, clock: FrozenClock) -> None:
        uc = ApproveFandomProposalUseCase(
            FakeUow(),
            FakeProposalRepo(),
            CreateFandomUseCase(FakeUow(), FakeFandomAdminRepo(), FakeAudit(), clock),
            FakeNotifier(),
            FakeAudit(),
            clock,
        )
        with pytest.raises(NotFoundError):
            await uc(ApproveFandomProposalCommand(actor_id=7, proposal_id=999))


# ---------- Reject ----------


class TestReject:
    @pytest.mark.asyncio
    async def test_reject_marks_and_notifies(self, clock: FrozenClock) -> None:
        repo = FakeProposalRepo()
        await repo.create(
            requested_by=UserId(42),
            name="X",
            category_hint="anime",
            comment=None,
            now=clock.now(),
        )
        notif = FakeNotifier()
        audit = FakeAudit()
        uc = RejectFandomProposalUseCase(FakeUow(), repo, notif, audit, clock)

        await uc(
            RejectFandomProposalCommand(actor_id=7, proposal_id=1, reason="дубль существующего")
        )

        p = await repo.get(ProposalId(1))
        assert p is not None and p.status is FandomProposalStatus.REJECTED
        assert p.decision_comment == "дубль существующего"
        assert notif.events == [
            ("rejected", {"to": 42, "name": "X", "reason": "дубль существующего"})
        ]
        assert any(e["action"] == "fandom_proposal.reject" for e in audit.entries)


# ---------- List ----------


class TestList:
    @pytest.mark.asyncio
    async def test_list_pending_returns_only_pending(self, clock: FrozenClock) -> None:
        repo = FakeProposalRepo()
        # Три заявки, одна одобрена — pending видны 2.
        for i, name in enumerate(["a", "b", "c"]):
            await repo.create(
                requested_by=UserId(40 + i),
                name=name,
                category_hint="anime",
                comment=None,
                now=clock.now(),
            )
        # Одобряем первую.
        p1 = await repo.get(ProposalId(1))
        assert p1 is not None
        p1.approve(
            moderator_id=UserId(7),
            fandom_id=FandomId(1),
            comment=None,
            now=clock.now(),
        )
        await repo.save(p1)

        uc = ListPendingFandomProposalsUseCase(repo)
        rows = await uc()
        assert {r.name for r in rows} == {"b", "c"}
