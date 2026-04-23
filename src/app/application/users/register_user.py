"""Use case: регистрация/обновление пользователя при /start."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.shared.ports import UnitOfWork
from app.application.tracking.ports import ITrackingRepository
from app.application.users.ports import IUserRepository
from app.core.clock import Clock
from app.domain.shared.types import UserId
from app.domain.tracking.entities import TrackingEvent
from app.domain.tracking.value_objects import TrackingCodeStr, TrackingEventType
from app.domain.users.entities import User


@dataclass(frozen=True, kw_only=True)
class RegisterUserCommand:
    tg_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    utm_code: str | None  # raw start payload; валидность проверим тут


@dataclass(frozen=True, kw_only=True)
class RegisterUserResult:
    user: User
    is_new: bool


class RegisterUserUseCase:
    """Идемпотентно: upsert пользователя, запись tracking_events('start') всегда,
    tracking_events('register') — только для новых."""

    def __init__(
        self,
        uow: UnitOfWork,
        users: IUserRepository,
        tracking: ITrackingRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._users = users
        self._tracking = tracking
        self._clock = clock

    async def __call__(self, cmd: RegisterUserCommand) -> RegisterUserResult:
        now = self._clock.now()
        async with self._uow:
            existing = await self._users.get(UserId(cmd.tg_id))
            is_new = existing is None
            code_id = None
            if cmd.utm_code:
                try:
                    code_str = TrackingCodeStr(cmd.utm_code)
                except Exception:
                    code_str = None
                if code_str is not None:
                    code_id = await self._tracking.get_code_id(str(code_str))

            if existing is None:
                user = User.register(
                    tg_id=cmd.tg_id,
                    username=cmd.username,
                    first_name=cmd.first_name,
                    last_name=cmd.last_name,
                    language_code=cmd.language_code,
                    utm_code_id=code_id,
                    now=now,
                )
            else:
                user = existing
                user.touch(
                    now=now,
                    username=cmd.username,
                    first_name=cmd.first_name,
                    last_name=cmd.last_name,
                    language_code=cmd.language_code,
                )

            await self._users.save(user)

            # tracking: пишем события ТОЛЬКО для новых пользователей, чтобы
            # трекинговая ссылка не раздувала переходы за счёт повторных
            # нажатий /start от уже зарегистрированных юзеров.
            if is_new:
                await self._tracking.record(
                    TrackingEvent(
                        id=None,
                        code_id=code_id,
                        user_id=user.id,
                        event_type=TrackingEventType.START,
                        payload={},
                        created_at=now,
                    )
                )
                await self._tracking.record(
                    TrackingEvent(
                        id=None,
                        code_id=code_id,
                        user_id=user.id,
                        event_type=TrackingEventType.REGISTER,
                        payload={},
                        created_at=now,
                    )
                )

            self._uow.record_events(user.pull_events())
            await self._uow.commit()

        return RegisterUserResult(user=user, is_new=is_new)
