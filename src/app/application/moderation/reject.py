"""Use case: модератор отклоняет фик с причинами и комментарием."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.fanfics.ports import (
    IAuthorNotifier,
    IChapterRepository,
    IFanficRepository,
    IOutboxRepository,
)
from app.application.moderation.ports import (
    IAuditLog,
    IModerationRepository,
    IReasonRepository,
)
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.fanfics.services import entity_validator
from app.domain.fanfics.value_objects import FicStatus
from app.domain.moderation.exceptions import (
    CaseAlreadyDecidedError,
    ReasonsRequiredForRejectError,
)
from app.domain.moderation.value_objects import REJECT_COMMENT_MAX, RejectionReason
from app.domain.shared.types import (
    FanficId,
    ModerationCaseId,
    ModerationReasonId,
    UserId,
)


@dataclass(frozen=True, kw_only=True)
class RejectCommand:
    case_id: int
    moderator_id: int
    reason_ids: list[int]
    comment: str | None = None
    comment_entities: list[dict[str, Any]] | None = None


class RejectUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        reasons: IReasonRepository,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        notifier: IAuthorNotifier,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._moderation = moderation
        self._reasons = reasons
        self._fanfics = fanfics
        self._chapters = chapters
        self._outbox = outbox
        self._audit = audit
        self._notifier = notifier
        self._clock = clock

    async def __call__(self, cmd: RejectCommand) -> None:
        now = self._clock.now()
        moderator_id = UserId(cmd.moderator_id)

        if not cmd.reason_ids:
            raise ReasonsRequiredForRejectError(
                "Выбери хотя бы одну причину отказа."
            )
        comment = (cmd.comment or "").strip() or None
        if comment is not None and len(comment) > REJECT_COMMENT_MAX:
            raise ReasonsRequiredForRejectError(
                f"Комментарий слишком длинный (>{REJECT_COMMENT_MAX} символов)."
            )
        entities = entity_validator.validate(comment or "", cmd.comment_entities)

        notify_author_id: UserId | None = None
        notify_fic_id: FanficId | None = None
        notify_title: str | None = None
        resolved_reasons: list[RejectionReason] = []

        async with self._uow:
            case = await self._moderation.get_by_id(ModerationCaseId(cmd.case_id))
            if case is None:
                raise NotFoundError("Задание не найдено.")
            case.raise_if_owned_by(moderator_id)
            # Авто-lock: если lock истёк/был снят — подхватываем для текущего мода.
            if not case.is_locked(now=now):
                case.lock(moderator_id=moderator_id, now=now)

            resolved_reasons = await self._reasons.get_by_ids(
                [ModerationReasonId(i) for i in cmd.reason_ids]
            )
            if len(resolved_reasons) != len(set(cmd.reason_ids)):
                raise NotFoundError("Некоторые причины не найдены.")

            case.reject(
                moderator_id=moderator_id,
                reason_ids=cmd.reason_ids,
                comment=comment,
                entities=entities,
                now=now,
            )
            updated = await self._moderation.save_decision_idempotent(case)
            if not updated:
                raise CaseAlreadyDecidedError("Другой модератор уже решил.")

            fic = await self._fanfics.get(case.fic_id)
            if fic is None:
                raise NotFoundError("Фик не найден.")

            fic.reject(reason_ids=cmd.reason_ids, now=now)
            await self._fanfics.save(fic)

            pending_chapters = await self._chapters.list_by_fic_and_statuses(
                fic.id, [FicStatus.PENDING]
            )
            for ch in pending_chapters:
                ch.reject(reason_ids=cmd.reason_ids, now=now)
                await self._chapters.save(ch)

            await self._audit.log(
                actor_id=moderator_id,
                action="fic.reject",
                target_type="fanfic",
                target_id=int(fic.id),
                payload={
                    "case_id": int(case.id),
                    "reason_ids": cmd.reason_ids,
                    "comment": comment,
                },
                now=now,
            )
            await self._outbox.append(
                event_type="fanfic.rejected",
                payload={
                    "fic_id": int(fic.id),
                    "author_id": int(fic.author_id),
                    "case_id": int(case.id),
                    "reason_ids": cmd.reason_ids,
                },
                now=now,
            )

            self._uow.record_events(case.pull_events() + fic.pull_events())
            for ch in pending_chapters:
                self._uow.record_events(ch.pull_events())
            await self._uow.commit()

            notify_author_id = fic.author_id
            notify_fic_id = fic.id
            notify_title = str(fic.title)

        if notify_author_id is not None and notify_fic_id is not None and notify_title is not None:
            try:
                await self._notifier.notify_rejected(
                    author_id=notify_author_id,
                    fic_id=notify_fic_id,
                    fic_title=notify_title,
                    reasons=resolved_reasons,
                    comment=comment,
                    comment_entities=entities,
                )
            except Exception:  # noqa: BLE001
                pass
