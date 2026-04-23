"""Use case: модератор обрабатывает жалобу (dismiss / action)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.application.fanfics.ports import (
    IFanficRepository,
    IOutboxRepository,
)
from app.application.moderation.ports import IAuditLog
from app.application.reports.ports import IReportRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError, ValidationError
from app.domain.fanfics.value_objects import FicStatus
from app.domain.reports.value_objects import ReportTarget
from app.domain.shared.types import FanficId, ReportId, UserId

DecisionLiteral = Literal["dismiss", "action"]


@dataclass(frozen=True, kw_only=True)
class HandleReportCommand:
    report_id: int
    moderator_id: int
    decision: DecisionLiteral
    comment: str | None = None
    # Для action: что именно сделать. В MVP — только "archive" (архивировать фик).
    action_kind: Literal["archive"] | None = None


@dataclass(frozen=True, kw_only=True)
class HandleReportResult:
    decision: DecisionLiteral
    archived_fic_id: int | None  # установлен, если action_kind=="archive"


class HandleReportUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        reports: IReportRepository,
        fanfics: IFanficRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._reports = reports
        self._fanfics = fanfics
        self._outbox = outbox
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: HandleReportCommand) -> HandleReportResult:
        if cmd.decision == "action" and cmd.action_kind is None:
            raise ValidationError("Для Action нужно указать action_kind.")

        moderator_id = UserId(cmd.moderator_id)
        now = self._clock.now()
        archived_fic_id: int | None = None
        archived_author_id: int | None = None
        archived_fic_title: str | None = None

        async with self._uow:
            report = await self._reports.get(ReportId(cmd.report_id))
            if report is None:
                raise NotFoundError("Жалоба не найдена.")

            if cmd.decision == "dismiss":
                report.dismiss(moderator_id=moderator_id, comment=cmd.comment, now=now)
                audit_action = "report.dismiss"
            else:
                archived = await self._apply_action(report.target_type, report.target_id, now=now)
                if archived is not None:
                    archived_fic_id, archived_author_id, archived_fic_title = archived
                report.action(moderator_id=moderator_id, comment=cmd.comment, now=now)
                audit_action = "report.action"

            await self._reports.save(report)

            await self._audit.log(
                actor_id=moderator_id,
                action=audit_action,
                target_type=report.target_type.value,
                target_id=int(report.target_id),
                payload={
                    "report_id": int(report.id),
                    "comment": cmd.comment,
                    "action_kind": cmd.action_kind,
                },
                now=now,
            )

            # Если фик был архивирован — два outbox-события:
            # 1. `fanfic.archived` → переиндексировать / удалить из Meili.
            # 2. `fanfic.archived_by_report` → уведомить автора (у него приватный
            #    месседж со ссылкой на правила и причиной).
            if archived_fic_id is not None:
                await self._outbox.append(
                    event_type="fanfic.archived",
                    payload={
                        "fic_id": int(archived_fic_id),
                        "reason": "report_actioned",
                        "report_id": int(report.id),
                    },
                    now=now,
                )
                if archived_author_id is not None:
                    await self._outbox.append(
                        event_type="fanfic.archived_by_report",
                        payload={
                            "fic_id": int(archived_fic_id),
                            "author_id": int(archived_author_id),
                            "fic_title": archived_fic_title or "",
                            "report_id": int(report.id),
                            "reason_code": report.reason_code,
                            "moderator_comment": cmd.comment,
                        },
                        now=now,
                    )

            # Всегда эмитим report.handled — диспетчер решит, слать ли
            # уведомление репортеру (по notify_reporter-флагу в payload).
            await self._outbox.append(
                event_type="report.handled",
                payload={
                    "report_id": int(report.id),
                    "reporter_id": int(report.reporter_id),
                    "target_type": report.target_type.value,
                    "target_id": int(report.target_id),
                    "decision": cmd.decision,
                    "notify_reporter": bool(report.notify_reporter),
                    "action_kind": cmd.action_kind,
                },
                now=now,
            )

            self._uow.record_events(report.pull_events())
            await self._uow.commit()

        return HandleReportResult(
            decision=cmd.decision,
            archived_fic_id=archived_fic_id,
        )

    async def _apply_action(
        self,
        target_type: ReportTarget,
        target_id: int,
        *,
        now: datetime,
    ) -> tuple[int, int, str] | None:
        """Применить action к цели жалобы. В MVP — только archive фика.

        Возвращает (fic_id, author_id, fic_title), если фик был архивирован;
        иначе None.
        """
        if target_type == ReportTarget.FANFIC:
            fic = await self._fanfics.get(FanficId(target_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            author_id = int(fic.author_id)
            fic_title = str(fic.title)
            if fic.status == FicStatus.ARCHIVED:
                # Уже архивирован — идемпотентно: без изменений, без ошибки.
                return int(fic.id), author_id, fic_title
            fic.archive(now=now)
            await self._fanfics.save(fic)
            return int(fic.id), author_id, fic_title

        if target_type == ReportTarget.CHAPTER:
            # В MVP chapter-level actions не поддержаны — модератор бьёт по
            # фику целиком (жалоба на главу → UI показывает подсказку).
            raise ValidationError("Action по главе пока не поддержан — используй жалобу на фик.")

        raise ValidationError(f"Action для target_type={target_type.value} не поддержан.")
