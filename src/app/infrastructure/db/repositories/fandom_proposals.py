"""PgFandomProposalRepository: CRUD заявок на фандом."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reference.ports import (
    FandomProposalRow,
    IFandomProposalRepository,
)
from app.core.errors import ConflictError
from app.domain.reference.entities import FandomProposal as ProposalEntity
from app.domain.reference.value_objects import FandomProposalStatus, ProposalId
from app.domain.shared.types import FandomId, UserId
from app.infrastructure.db.models.fandom_proposal import (
    FandomProposal as ProposalModel,
)


def _to_entity(m: ProposalModel) -> ProposalEntity:
    return ProposalEntity(
        id=ProposalId(int(m.id)),
        requested_by=UserId(int(m.requested_by)),
        name=str(m.name),
        category_hint=str(m.category_hint),
        comment=m.comment,
        status=FandomProposalStatus(m.status),
        reviewed_by=UserId(int(m.reviewed_by)) if m.reviewed_by is not None else None,
        reviewed_at=m.reviewed_at,
        decision_comment=m.decision_comment,
        created_fandom_id=FandomId(int(m.created_fandom_id))
        if m.created_fandom_id is not None
        else None,
        created_at=m.created_at,
    )


def _to_row(m: ProposalModel) -> FandomProposalRow:
    return FandomProposalRow(
        id=ProposalId(int(m.id)),
        name=str(m.name),
        category_hint=str(m.category_hint),
        comment=m.comment,
        requested_by=UserId(int(m.requested_by)),
        status=str(m.status.value if hasattr(m.status, "value") else m.status),
        reviewed_by=UserId(int(m.reviewed_by)) if m.reviewed_by is not None else None,
        reviewed_at=m.reviewed_at,
        decision_comment=m.decision_comment,
        created_fandom_id=FandomId(int(m.created_fandom_id))
        if m.created_fandom_id is not None
        else None,
        created_at=m.created_at,
    )


class PgFandomProposalRepository(IFandomProposalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        requested_by: UserId,
        name: str,
        category_hint: str,
        comment: str | None,
        now: datetime,
    ) -> ProposalEntity:
        # Pre-check анти-дубля под защитой partial-unique индекса.
        # Гонка двух одновременных INSERT остаётся защищённой на уровне БД —
        # IntegrityError тогда дойдёт до UoW и поднимет наверх как ConflictError.
        dup_stmt = (
            select(ProposalModel.id)
            .where(
                ProposalModel.requested_by == int(requested_by),
                func.lower(ProposalModel.name) == name.lower(),
                ProposalModel.status == FandomProposalStatus.PENDING,
            )
            .limit(1)
        )
        if (await self._s.execute(dup_stmt)).scalar_one_or_none() is not None:
            raise ConflictError("У тебя уже есть открытая заявка с таким названием.")

        m = ProposalModel(
            requested_by=int(requested_by),
            name=name,
            category_hint=category_hint,
            comment=comment,
            status=FandomProposalStatus.PENDING,
            created_at=now,
        )
        self._s.add(m)
        await self._s.flush()
        return _to_entity(m)

    async def get(self, proposal_id: ProposalId) -> ProposalEntity | None:
        m = await self._s.get(ProposalModel, int(proposal_id))
        return _to_entity(m) if m else None

    async def save(self, proposal: ProposalEntity) -> None:
        stmt = (
            update(ProposalModel)
            .where(ProposalModel.id == int(proposal.id))
            .values(
                status=proposal.status,
                reviewed_by=int(proposal.reviewed_by) if proposal.reviewed_by is not None else None,
                reviewed_at=proposal.reviewed_at,
                decision_comment=proposal.decision_comment,
                created_fandom_id=int(proposal.created_fandom_id)
                if proposal.created_fandom_id is not None
                else None,
            )
        )
        await self._s.execute(stmt)
        await self._s.flush()

    async def list_pending(self, *, limit: int = 50) -> list[FandomProposalRow]:
        stmt = (
            select(ProposalModel)
            .where(ProposalModel.status == FandomProposalStatus.PENDING)
            .order_by(ProposalModel.created_at.asc())
            .limit(limit)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_row(m) for m in rows]

    async def list_recent(
        self, *, status: str | None = None, limit: int = 50
    ) -> list[FandomProposalRow]:
        stmt = select(ProposalModel).order_by(ProposalModel.created_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(ProposalModel.status == FandomProposalStatus(status))
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_row(m) for m in rows]
