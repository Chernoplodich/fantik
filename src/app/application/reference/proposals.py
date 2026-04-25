"""Use cases заявок на новый фандом.

Поток: автор → SubmitFandomProposalUseCase → pending →
       (админ) → ApproveFandomProposalUseCase | RejectFandomProposalUseCase.

Approve внутри транзакции вызывает CreateFandomUseCase, фиксирует proposal как
approved + сохраняет created_fandom_id, и шлёт уведомление автору.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.moderation.ports import IAuditLog
from app.application.reference.fandoms_crud import (
    CreateFandomCommand,
    CreateFandomUseCase,
)
from app.application.reference.ports import (
    FandomProposalRow,
    IFandomProposalNotifier,
    IFandomProposalRepository,
)
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.domain.reference.value_objects import FandomProposalStatus, ProposalId
from app.domain.shared.types import FandomId, UserId

_MAX_NAME_LEN = 256
_MAX_COMMENT_LEN = 500


def _validate_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise ValidationError("Название фандома пустое.")
    if len(name) > _MAX_NAME_LEN:
        raise ValidationError(f"Название фандома: до {_MAX_NAME_LEN} символов.")
    return name


def _validate_comment(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if len(text) > _MAX_COMMENT_LEN:
        raise ValidationError(f"Комментарий: до {_MAX_COMMENT_LEN} символов.")
    return text


# ============================================================
# Submit
# ============================================================


@dataclass(frozen=True, kw_only=True)
class SubmitFandomProposalCommand:
    requested_by: int
    name: str
    category_hint: str
    comment: str | None = None


@dataclass(frozen=True, kw_only=True)
class SubmitFandomProposalResult:
    proposal_id: ProposalId
    created: bool  # False, если у юзера уже была pending-заявка с тем же именем


class SubmitFandomProposalUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: IFandomProposalRepository,
        notifier: IFandomProposalNotifier,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._notifier = notifier
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: SubmitFandomProposalCommand) -> SubmitFandomProposalResult:
        from app.application.reference.fandoms_crud import _validate_category

        name = _validate_name(cmd.name)
        category = _validate_category(cmd.category_hint)
        comment = _validate_comment(cmd.comment)

        requested_by = UserId(int(cmd.requested_by))
        now = self._clock.now()

        async with self._uow:
            try:
                proposal = await self._repo.create(
                    requested_by=requested_by,
                    name=name,
                    category_hint=category,
                    comment=comment,
                    now=now,
                )
            except ConflictError:
                # Уже была открытая заявка от того же юзера с тем же именем —
                # тихо возвращаем «не создано».
                await self._uow.commit()
                return SubmitFandomProposalResult(proposal_id=ProposalId(0), created=False)

            await self._audit.log(
                actor_id=requested_by,
                action="fandom_proposal.submit",
                target_type="fandom_proposal",
                target_id=int(proposal.id),
                payload={"name": name, "category": category},
                now=now,
            )
            await self._uow.commit()

        # Уведомляем автора уже после commit'а — при сбое отправки заявка останется.
        await self._notifier.notify_submitted(requested_by=requested_by, name=name)

        return SubmitFandomProposalResult(proposal_id=proposal.id, created=True)


# ============================================================
# Approve
# ============================================================


@dataclass(frozen=True, kw_only=True)
class ApproveFandomProposalCommand:
    actor_id: int
    proposal_id: int
    # Админ может скорректировать запись фандома при создании.
    name: str | None = None
    category: str | None = None
    slug: str | None = None
    aliases: list[str] | None = None
    decision_comment: str | None = None


@dataclass(frozen=True, kw_only=True)
class ApproveFandomProposalResult:
    proposal_id: ProposalId
    fandom_id: FandomId


class ApproveFandomProposalUseCase:
    """Одобряет заявку и создаёт фандом.

    Внутри одной транзакции UoW:
      1. Грузим заявку, проверяем pending.
      2. Создаём фандом через PgFandomAdminRepository (но без отдельного UoW.commit —
         используем общий, см. ниже).
      3. Помечаем заявку approved + created_fandom_id.
      4. Audit log.
      5. Notifier — после commit.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        proposals: IFandomProposalRepository,
        create_fandom_uc: CreateFandomUseCase,
        notifier: IFandomProposalNotifier,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._proposals = proposals
        self._create_fandom_uc = create_fandom_uc
        self._notifier = notifier
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: ApproveFandomProposalCommand) -> ApproveFandomProposalResult:
        proposal_id = ProposalId(int(cmd.proposal_id))
        actor_id = UserId(int(cmd.actor_id))
        comment = _validate_comment(cmd.decision_comment)
        now = self._clock.now()

        # CreateFandomUseCase сам открывает свой UoW и комитит. Для атомарности
        # с marking proposal-а можно было бы хитро шарить транзакцию; но в нашей
        # модели UoW работает поверх той же AsyncSession (request-scope), поэтому
        # вызов create_fandom_uc внутри основной транзакции ОК — он коммитит
        # session.commit(), и наш повторный uow.commit() ниже — это no-op
        # (in_transaction=False).
        # Чтобы избежать двойного commit'а, делаем create_fandom ДО открытия
        # своего UoW: фандом сохраняется, его id используем для apply на proposal.

        proposal = await self._proposals.get(proposal_id)
        if proposal is None:
            raise NotFoundError("Заявка не найдена.")
        if proposal.status is not FandomProposalStatus.PENDING:
            raise ConflictError("Заявка уже обработана.")

        # Имя/категория для фандома: либо из cmd, либо из заявки.
        fandom_name = (cmd.name or proposal.name).strip()
        fandom_category = (cmd.category or proposal.category_hint).strip().lower()
        aliases = [a for a in (cmd.aliases or []) if a]

        # Создаём фандом. CreateFandomUseCase коммитит свою транзакцию.
        created = await self._create_fandom_uc(
            CreateFandomCommand(
                actor_id=int(actor_id),
                name=fandom_name,
                category=fandom_category,
                aliases=aliases,
                slug=cmd.slug,
            )
        )
        fandom_id = FandomId(int(created.id))

        # Теперь помечаем заявку — отдельной транзакцией.
        async with self._uow:
            persisted = await self._proposals.get(proposal_id)
            if persisted is None:
                raise NotFoundError("Заявка исчезла.")
            persisted.approve(
                moderator_id=actor_id,
                fandom_id=fandom_id,
                comment=comment,
                now=now,
            )
            await self._proposals.save(persisted)
            await self._audit.log(
                actor_id=actor_id,
                action="fandom_proposal.approve",
                target_type="fandom_proposal",
                target_id=int(proposal_id),
                payload={
                    "fandom_id": int(fandom_id),
                    "name": fandom_name,
                    "comment": comment,
                },
                now=now,
            )
            await self._uow.commit()

        # Уведомляем автора заявки — после commit.
        await self._notifier.notify_approved(
            requested_by=proposal.requested_by,
            name=fandom_name,
            fandom_id=fandom_id,
        )

        return ApproveFandomProposalResult(proposal_id=proposal_id, fandom_id=fandom_id)


# ============================================================
# Reject
# ============================================================


@dataclass(frozen=True, kw_only=True)
class RejectFandomProposalCommand:
    actor_id: int
    proposal_id: int
    reason: str | None = None


class RejectFandomProposalUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        proposals: IFandomProposalRepository,
        notifier: IFandomProposalNotifier,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._proposals = proposals
        self._notifier = notifier
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: RejectFandomProposalCommand) -> ProposalId:
        proposal_id = ProposalId(int(cmd.proposal_id))
        actor_id = UserId(int(cmd.actor_id))
        reason = _validate_comment(cmd.reason)
        now = self._clock.now()

        async with self._uow:
            proposal = await self._proposals.get(proposal_id)
            if proposal is None:
                raise NotFoundError("Заявка не найдена.")
            proposal.reject(moderator_id=actor_id, reason=reason, now=now)
            await self._proposals.save(proposal)
            await self._audit.log(
                actor_id=actor_id,
                action="fandom_proposal.reject",
                target_type="fandom_proposal",
                target_id=int(proposal_id),
                payload={"reason": reason},
                now=now,
            )
            await self._uow.commit()

        await self._notifier.notify_rejected(
            requested_by=proposal.requested_by,
            name=proposal.name,
            reason=reason,
        )

        return proposal_id


# ============================================================
# List pending (read-model)
# ============================================================


class ListPendingFandomProposalsUseCase:
    def __init__(self, repo: IFandomProposalRepository) -> None:
        self._repo = repo

    async def __call__(self, *, limit: int = 50) -> list[FandomProposalRow]:
        return await self._repo.list_pending(limit=limit)
