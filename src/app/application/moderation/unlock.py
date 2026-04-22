"""Use case: модератор снимает свой lock вручную."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.moderation.ports import IModerationRepository
from app.application.shared.ports import UnitOfWork
from app.core.errors import NotFoundError
from app.domain.moderation.exceptions import CaseNotLockedByThisModeratorError
from app.domain.shared.types import ModerationCaseId, UserId


@dataclass(frozen=True, kw_only=True)
class UnlockCommand:
    case_id: int
    moderator_id: int


class UnlockCaseUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
    ) -> None:
        self._uow = uow
        self._moderation = moderation

    async def __call__(self, cmd: UnlockCommand) -> None:
        async with self._uow:
            case = await self._moderation.get_by_id(ModerationCaseId(cmd.case_id))
            if case is None:
                raise NotFoundError("Задание не найдено.")
            if case.locked_by != UserId(cmd.moderator_id):
                raise CaseNotLockedByThisModeratorError(
                    "Снять lock может только тот модератор, который его поставил."
                )
            ok = await self._moderation.unlock(
                case_id=case.id, moderator_id=UserId(cmd.moderator_id)
            )
            if not ok:
                raise CaseNotLockedByThisModeratorError("Lock не снят.")
            await self._uow.commit()
