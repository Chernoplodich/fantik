"""Use case: самоудаление пользователя (`/delete_me`).

Следует docs/12-security-privacy.md §«Право на удаление»:

- `author_nick` → `deleted_<hash8>`; `username`, `first_name`, `last_name` → NULL.
- `utm_source_code_id` → NULL.
- draft / rejected / revising работы — полностью удаляются (каскадно с главами).
- approved / pending / archived — остаются (контракт с читателями).
- Пользовательский контент: `bookmarks`, `likes`, `reading_progress`,
  `reads_completed`, `subscriptions` (subscriber и author), `reports`,
  `notifications` — DELETE.
- `tracking_events.user_id` → NULL (события остаются для статистики).
- `banned_at=now`, `banned_reason='self_deleted'` — защита от повторной
  регистрации того же `tg_id`.
- audit_log — сохраняется, плюс добавляется запись `user.self_deleted`.

Всё — внутри одной транзакции. Идемпотентно: повторный вызов — no-op.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.moderation.ports import IAuditLog
from app.application.shared.ports import UnitOfWork
from app.application.users.ports import IUserRepository
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.domain.shared.types import UserId

log = get_logger(__name__)

SELF_DELETED_REASON = "self_deleted"


@dataclass(frozen=True, kw_only=True)
class DeleteUserCommand:
    user_id: int


def _anonymized_nick(tg_id: int) -> str:
    h = hashlib.sha256(str(tg_id).encode()).hexdigest()[:8]
    return f"deleted_{h}"


class DeleteUserUseCase:
    """Анонимизация + каскадное удаление персонального контента."""

    def __init__(
        self,
        uow: UnitOfWork,
        users: IUserRepository,
        session: AsyncSession,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._users = users
        self._s = session
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: DeleteUserCommand) -> None:
        user_id = UserId(int(cmd.user_id))
        now = self._clock.now()

        async with self._uow:
            user = await self._users.get(user_id)
            if user is None:
                raise NotFoundError("Пользователь не найден.")

            # Уже self-deleted — повторный вызов безопасен, просто возвращаемся.
            if user.banned_reason == SELF_DELETED_REASON:
                await self._uow.commit()
                return

            new_nick = _anonymized_nick(int(user_id))
            anonymize_sql = text(
                """
                UPDATE users
                   SET author_nick = :new_nick,
                       username = NULL,
                       first_name = NULL,
                       last_name = NULL,
                       utm_source_code_id = NULL,
                       banned_at = :now,
                       banned_reason = :reason
                 WHERE id = :uid
                """
            )
            await self._s.execute(
                anonymize_sql,
                {
                    "new_nick": new_nick,
                    "now": now,
                    "reason": SELF_DELETED_REASON,
                    "uid": int(user_id),
                },
            )

            # Неопубликованные работы уходят полностью: удаляем fanfic_tags,
            # затем chapters (CASCADE на chapter_pages / chapter_pending),
            # fanfic_versions, fanfics.
            await self._s.execute(
                text(
                    """
                    DELETE FROM fanfics
                     WHERE author_id = :uid
                       AND status IN ('draft','rejected','revising')
                    """
                ),
                {"uid": int(user_id)},
            )

            # Персональное — всё DELETE. LEFT OUTER на несуществующие таблицы
            # избегаем, т.к. все они присутствуют к Этапу 7.
            for tbl, uid_col in [
                ("bookmarks", "user_id"),
                ("likes", "user_id"),
                ("reading_progress", "user_id"),
                ("reads_completed", "user_id"),
                ("notifications", "user_id"),
                ("reports", "reporter_id"),
            ]:
                await self._s.execute(
                    text(f"DELETE FROM {tbl} WHERE {uid_col} = :uid"),
                    {"uid": int(user_id)},
                )
            # Подписки обоих направлений (юзер как подписчик и как автор).
            await self._s.execute(
                text("DELETE FROM subscriptions WHERE subscriber_id = :uid OR author_id = :uid"),
                {"uid": int(user_id)},
            )

            # tracking_events — обезличиваем, события сохраняем.
            await self._s.execute(
                text("UPDATE tracking_events SET user_id = NULL WHERE user_id = :uid"),
                {"uid": int(user_id)},
            )

            await self._audit.log(
                actor_id=user_id,
                action="user.self_deleted",
                target_type="user",
                target_id=int(user_id),
                payload={"new_nick": new_nick},
                now=now,
            )

            await self._uow.commit()

        log.info("user_self_deleted", user_id=int(user_id), new_nick=new_nick)
