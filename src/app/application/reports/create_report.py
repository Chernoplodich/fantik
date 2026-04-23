"""Use case: читатель создаёт жалобу на фик или главу."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.fanfics.ports import (
    IChapterRepository,
    IFanficRepository,
    IOutboxRepository,
)
from app.application.moderation.ports import IAuditLog
from app.application.reports.ports import IReportRepository
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError, ValidationError
from app.domain.reports.events import ReportSubmitted
from app.domain.reports.exceptions import SelfReportError
from app.domain.reports.value_objects import REPORT_REASON_CODES, ReportTarget
from app.domain.shared.types import ChapterId, FanficId, ReportId, UserId


@dataclass(frozen=True, kw_only=True)
class CreateReportCommand:
    reporter_id: int
    target_type: ReportTarget
    target_id: int
    reason_code: str | None
    text: str | None
    text_entities: list[dict[str, Any]] | None = None
    notify_reporter: bool = True


@dataclass(frozen=True, kw_only=True)
class CreateReportResult:
    report_id: ReportId
    created: bool  # False если у репортера уже была open-жалоба на ту же цель


class CreateReportUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        reports: IReportRepository,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._reports = reports
        self._fanfics = fanfics
        self._chapters = chapters
        self._outbox = outbox
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: CreateReportCommand) -> CreateReportResult:
        if cmd.reason_code is not None and cmd.reason_code not in REPORT_REASON_CODES:
            raise ValidationError("Недопустимый код причины жалобы.")
        if cmd.text is not None and len(cmd.text) > 2000:
            raise ValidationError("Комментарий слишком длинный (до 2000 символов).")

        reporter_id = UserId(cmd.reporter_id)
        now = self._clock.now()

        async with self._uow:
            # Резолвим автора цели, чтобы защититься от self-report.
            author_id = await self._resolve_target_author(cmd.target_type, cmd.target_id)
            if author_id is None:
                raise NotFoundError("Цель жалобы не найдена.")
            if reporter_id == author_id:
                raise SelfReportError("Нельзя жаловаться на свою работу.")

            # Анти-дубль: если у репортера уже есть open-жалоба на ту же цель —
            # не создаём новую, возвращаем существующую.
            existing = await self._reports.exists_open_from_reporter(
                reporter_id=reporter_id,
                target_type=cmd.target_type,
                target_id=cmd.target_id,
            )
            if existing is not None:
                await self._uow.commit()
                return CreateReportResult(report_id=existing, created=False)

            report = await self._reports.create(
                reporter_id=reporter_id,
                target_type=cmd.target_type,
                target_id=cmd.target_id,
                reason_code=cmd.reason_code,
                text=cmd.text,
                text_entities=list(cmd.text_entities or []),
                notify_reporter=cmd.notify_reporter,
                now=now,
            )

            await self._outbox.append(
                event_type="report.created",
                payload={
                    "report_id": int(report.id),
                    "reporter_id": int(reporter_id),
                    "target_type": cmd.target_type.value,
                    "target_id": int(cmd.target_id),
                    "reason_code": cmd.reason_code,
                },
                now=now,
            )
            await self._audit.log(
                actor_id=reporter_id,
                action="report.create",
                target_type=cmd.target_type.value,
                target_id=int(cmd.target_id),
                payload={
                    "report_id": int(report.id),
                    "reason_code": cmd.reason_code,
                },
                now=now,
            )
            self._uow.record_events(
                [
                    ReportSubmitted(
                        report_id=report.id,
                        reporter_id=reporter_id,
                        target_type=cmd.target_type,
                        target_id=int(cmd.target_id),
                    )
                ]
            )
            await self._uow.commit()
            return CreateReportResult(report_id=report.id, created=True)

    async def _resolve_target_author(
        self, target_type: ReportTarget, target_id: int
    ) -> UserId | None:
        """Достать author_id объекта жалобы (пока поддерживаем fanfic и chapter)."""
        if target_type == ReportTarget.FANFIC:
            fic = await self._fanfics.get(FanficId(target_id))
            return fic.author_id if fic else None
        if target_type == ReportTarget.CHAPTER:
            ch = await self._chapters.get(ChapterId(target_id))
            if ch is None:
                return None
            fic = await self._fanfics.get(ch.fic_id)
            return fic.author_id if fic else None
        # USER / COMMENT — не поддержаны в MVP (пост-MVP).
        return None
