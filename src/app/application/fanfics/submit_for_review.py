"""Use case: отправить фик на модерацию.

Транзакционно: fanfic → pending, все draft/rejected/revising chapters → pending,
fanfic_versions snapshot, moderation_queue INSERT, outbox event, last_edit_at.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import (
    IChapterRepository,
    IFanficRepository,
    IFanficVersionRepository,
    IOutboxRepository,
)
from app.application.moderation.ports import (
    IModerationRepository,
    IModeratorNotifier,
)
from app.application.shared.ports import UnitOfWork
from app.application.users.ports import IUserRepository
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.domain.fanfics.exceptions import (
    EmptyFanficError,
    ForbiddenActionError,
    TooManyDailySubmissionsError,
)
from app.domain.fanfics.value_objects import FicStatus, MqKind
from app.domain.shared.types import FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class SubmitForReviewCommand:
    fic_id: int
    author_id: int


@dataclass(frozen=True, kw_only=True)
class SubmitForReviewResult:
    case_id: int
    kind: MqKind
    version_no: int


class SubmitForReviewUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        versions: IFanficVersionRepository,
        moderation: IModerationRepository,
        outbox: IOutboxRepository,
        users: IUserRepository,
        clock: Clock,
        settings: Settings,
        mod_notifier: IModeratorNotifier | None = None,
    ) -> None:
        self._uow = uow
        self._fanfics = fanfics
        self._chapters = chapters
        self._mod_notifier = mod_notifier
        self._versions = versions
        self._moderation = moderation
        self._outbox = outbox
        self._users = users
        self._clock = clock
        self._settings = settings

    async def __call__(self, cmd: SubmitForReviewCommand) -> SubmitForReviewResult:
        now = self._clock.now()
        async with self._uow:
            fic = await self._fanfics.get(FanficId(cmd.fic_id))
            if fic is None:
                raise NotFoundError("Фик не найден.")
            author_id = UserId(cmd.author_id)
            if fic.author_id != author_id:
                raise ForbiddenActionError("Нельзя отправлять на модерацию чужой фик.")

            author = await self._users.get(author_id)
            if author is None:
                raise NotFoundError("Пользователь не найден.")

            # дневной лимит подач (по fanfics.created_at в TZ автора)
            already = await self._fanfics.count_submitted_today(
                author_id=author_id, tz=author.timezone
            )
            # если это повторный submit уже существующего фика — не учитываем
            # (created_at старше today_start). count_submitted_today ограничен
            # рамкой "созданных сегодня", так что fic.created_at <= today:
            # реальный запрос должен учесть is_this_first_submit...
            # MVP: считаем, что повторный submit не увеличивает счётчик.
            # Если fic создан сегодня И это первый submit — лимит уже учтён на create.
            # На submit ещё раз считаем для защиты: лимитируем число фиков, чьё
            # первое состояние не-draft датировано сегодня.

            chapters_list = await self._chapters.list_by_fic(fic.id)
            if not chapters_list:
                raise EmptyFanficError("Нельзя отправить фик без глав.")

            is_first_submit = (fic.first_published_at is None
                               and fic.status in (FicStatus.DRAFT, FicStatus.REJECTED,
                                                  FicStatus.REVISING))

            # лимит: считаем только для первого submit (новые фики, поданные сегодня).
            if is_first_submit and already >= self._settings.max_fics_per_day:
                raise TooManyDailySubmissionsError(
                    f"Лимит {self._settings.max_fics_per_day} подач новых фиков в день."
                )

            # kind до перехода fanfic в pending
            kind = (
                MqKind.FIC_FIRST_PUBLISH
                if fic.first_published_at is None
                else MqKind.FIC_EDIT
            )

            # перевод глав (только тех, что требуют: draft/rejected/revising)
            for ch in chapters_list:
                if ch.status in (FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING):
                    ch.mark_pending(now=now)
                    await self._chapters.save(ch)

            fic.submit_for_review(now=now)
            await self._fanfics.save(fic)

            version_no = await self._versions.next_version_no(fic.id)
            snapshot = [
                {
                    "chapter_id": int(ch.id),
                    "number": int(ch.number),
                    "title": str(ch.title),
                    "chars_count": int(ch.chars_count),
                    "status": str(ch.status),
                }
                for ch in chapters_list
            ]
            await self._versions.create_snapshot(
                fic_id=fic.id,
                version_no=version_no,
                title=str(fic.title),
                summary=str(fic.summary),
                summary_entities=list(fic.summary_entities),
                snapshot_chapters=snapshot,
                now=now,
            )

            case = await self._moderation.create_case(
                fic_id=fic.id,
                chapter_id=None,
                kind=kind,
                submitted_by=author_id,
                now=now,
            )

            await self._outbox.append(
                event_type="fanfic.submitted",
                payload={
                    "fic_id": int(fic.id),
                    "author_id": int(author_id),
                    "kind": str(kind),
                    "case_id": int(case.id),
                    "version_no": version_no,
                },
                now=now,
            )

            self._uow.record_events(fic.pull_events() + case.pull_events())
            await self._uow.commit()

            notify_payload = (case.id, str(kind), fic.id, str(fic.title), author_id)

        if self._mod_notifier is not None:
            try:
                await self._mod_notifier.notify_new_case(
                    case_id=notify_payload[0],
                    kind=notify_payload[1],
                    fic_id=notify_payload[2],
                    fic_title=notify_payload[3],
                    author_id=notify_payload[4],
                )
            except Exception:  # noqa: BLE001 — нотификации не роллбэкают БД
                pass

        return SubmitForReviewResult(
            case_id=int(case.id), kind=kind, version_no=version_no
        )
