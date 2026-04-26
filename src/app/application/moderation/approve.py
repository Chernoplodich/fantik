"""Use case: модератор одобряет fanfic (через case)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.fanfics.ports import (
    IAuthorNotifier,
    IChapterRepository,
    IFanficRepository,
    IFanficVersionRepository,
    IOutboxRepository,
)
from app.application.moderation.ports import IAuditLog, IModerationRepository
from app.application.shared.ports import UnitOfWork
from app.application.tracking.record_event import (
    RecordEventCommand,
    RecordEventUseCase,
)
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.metrics import MODERATION_DECISION_LATENCY, MODERATION_DECISIONS
from app.domain.fanfics.value_objects import FicStatus
from app.domain.moderation.exceptions import CaseAlreadyDecidedError
from app.domain.shared.types import FanficId, FanficVersionId, ModerationCaseId, UserId
from app.domain.tracking.value_objects import TrackingEventType

log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class ApproveCommand:
    case_id: int
    moderator_id: int
    comment: str | None = None
    comment_entities: list[dict[str, Any]] | None = None


class ApproveUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        moderation: IModerationRepository,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        versions: IFanficVersionRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        notifier: IAuthorNotifier,
        clock: Clock,
        record_event: RecordEventUseCase | None = None,
    ) -> None:
        self._uow = uow
        self._moderation = moderation
        self._fanfics = fanfics
        self._chapters = chapters
        self._versions = versions
        self._outbox = outbox
        self._audit = audit
        self._notifier = notifier
        self._clock = clock
        # Опциональный — для тестов; в DI всегда инжектится реальный.
        self._record_event = record_event

    async def __call__(self, cmd: ApproveCommand) -> None:
        now = self._clock.now()
        moderator_id = UserId(cmd.moderator_id)
        entities = list(cmd.comment_entities or [])

        notify_author_id: UserId | None = None
        notify_fic_id: FanficId | None = None
        notify_title: str | None = None

        async with self._uow:
            case = await self._moderation.get_by_id(ModerationCaseId(cmd.case_id))
            if case is None:
                raise NotFoundError("Задание не найдено.")
            case.raise_if_owned_by(moderator_id)
            # Авто-lock: если lock истёк/был снят — подхватываем для текущего мода.
            if not case.is_locked(now=now):
                case.lock(moderator_id=moderator_id, now=now)
            case.approve(
                moderator_id=moderator_id,
                comment=cmd.comment,
                entities=entities,
                now=now,
            )
            updated = await self._moderation.save_decision_idempotent(case)
            if not updated:
                raise CaseAlreadyDecidedError("Другой модератор уже решил.")

            fic = await self._fanfics.get(case.fic_id)
            if fic is None:
                raise NotFoundError("Фик не найден.")

            version_id = await self._versions.get_latest_id(fic.id)
            if version_id is None:
                version_id = FanficVersionId(0)

            was_first_publish = fic.first_published_at is None
            fic.approve(version_id=version_id, now=now)
            await self._fanfics.save(fic)

            pending_chapters = await self._chapters.list_by_fic_and_statuses(
                fic.id, [FicStatus.PENDING]
            )
            # Отделяем «новые» главы (раньше никогда не одобрялись) от правок
            # уже одобренных — до мутации, т.к. approve() проставит
            # first_approved_at и обе группы в итоге будут иметь значение.
            new_chapter_ids = [
                int(ch.id) for ch in pending_chapters if not ch.was_previously_approved()
            ]
            for ch in pending_chapters:
                ch.approve(now=now)
                await self._chapters.save(ch)

            # Для репагинации: при first_publish главы все уже approved (вся книга),
            # при правке approved-фика — только что переведённые (pending → approved).
            if was_first_publish:
                approved_chapters = await self._chapters.list_by_fic_and_statuses(
                    fic.id, [FicStatus.APPROVED]
                )
            else:
                approved_chapters = list(pending_chapters)
            approved_chapter_ids = [int(ch.id) for ch in approved_chapters]

            await self._audit.log(
                actor_id=moderator_id,
                action="fic.approve",
                target_type="fanfic",
                target_id=int(fic.id),
                payload={
                    "case_id": int(case.id),
                    "comment": cmd.comment,
                    "first_publish": was_first_publish,
                },
                now=now,
            )
            await self._outbox.append(
                event_type="fanfic.approved",
                payload={
                    "fic_id": int(fic.id),
                    "author_id": int(fic.author_id),
                    "case_id": int(case.id),
                    "first_publish": was_first_publish,
                    "version_id": int(version_id),
                    "chapter_ids": approved_chapter_ids,
                    # kind модерационного кейса — справочно (диспетчер больше
                    # не опирается на него для fanout-решений).
                    "kind": case.kind.value,
                    # Главы, которые одобрены впервые — по ним шлём fanout
                    # подписчикам автора. При fic_first_publish поле пустое:
                    # там fanout определяется флагом first_publish.
                    "new_chapter_ids": new_chapter_ids,
                },
                now=now,
            )

            self._uow.record_events(case.pull_events() + fic.pull_events())
            for ch in pending_chapters:
                self._uow.record_events(ch.pull_events())
            await self._uow.commit()

            MODERATION_DECISIONS.labels(decision="approve").inc()
            submitted_at = getattr(case, "created_at", None) or getattr(case, "locked_at", None)
            if submitted_at is not None:
                MODERATION_DECISION_LATENCY.observe(max(0.0, (now - submitted_at).total_seconds()))

            notify_author_id = fic.author_id
            notify_fic_id = fic.id
            notify_title = str(fic.title)

        if notify_author_id is not None and notify_fic_id is not None and notify_title is not None:
            try:
                await self._notifier.notify_approved(
                    author_id=notify_author_id,
                    fic_id=notify_fic_id,
                    fic_title=notify_title,
                )
            except Exception:
                pass

        # tracking-событие `first_publish`: пишется один раз на автора при
        # самом первом одобрении его фика (`fic.first_published_at IS NULL`
        # в момент входа в use case). only_once=True страхует от дублей,
        # если флаг was_first_publish ошибочно проставится дважды.
        # Тоже после commit — чтобы при крахе approve-транзакции не было
        # фантомного события в воронке.
        if was_first_publish and notify_author_id is not None and self._record_event is not None:
            try:
                await self._record_event(
                    RecordEventCommand(
                        user_id=int(notify_author_id),
                        event_type=TrackingEventType.FIRST_PUBLISH,
                        payload={"fic_id": int(notify_fic_id) if notify_fic_id else 0},
                        only_once=True,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "first_publish_record_failed", exc=str(exc), author_id=int(notify_author_id)
                )
