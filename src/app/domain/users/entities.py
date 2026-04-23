"""Агрегат User."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.shared.events import EventEmitter
from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.users.events import (
    AuthorNickSet,
    UserBanned,
    UserRegistered,
    UserRoleChanged,
    UserUnbanned,
)
from app.domain.users.exceptions import (
    AuthorNickAlreadySetError,
)
from app.domain.users.value_objects import AuthorNick, Role


@dataclass
class User(EventEmitter):
    """Агрегат: пользователь Telegram-бота.

    Идентичность == tg_id.
    Ник автора задаётся единожды (политика MVP).
    """

    id: UserId
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    timezone: str = "Europe/Moscow"
    role: Role = Role.USER
    author_nick: AuthorNick | None = None
    utm_source_code_id: TrackingCodeId | None = None
    agreed_at: datetime | None = None
    banned_at: datetime | None = None
    banned_reason: str | None = None
    created_at: datetime | None = None
    last_seen_at: datetime | None = None

    def __post_init__(self) -> None:  # инициализация EventEmitter
        EventEmitter.__init__(self)
        # по умолчанию события не эмитим — только явные методы ниже

    # ---------- фабричные ----------

    @classmethod
    def register(
        cls,
        *,
        tg_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
        utm_code_id: TrackingCodeId | None,
        now: datetime,
    ) -> User:
        uid = UserId(tg_id)
        user = cls(
            id=uid,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            utm_source_code_id=utm_code_id,
            created_at=now,
            last_seen_at=now,
        )
        user._emit(UserRegistered(user_id=uid, utm_code_id=utm_code_id))
        return user

    # ---------- бизнес-операции ----------

    def touch(
        self,
        *,
        now: datetime,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> None:
        """Обновить профиль при очередном апдейте. Не эмитит события."""
        self.last_seen_at = now
        if username is not None:
            self.username = username
        if first_name is not None:
            self.first_name = first_name
        if last_name is not None:
            self.last_name = last_name
        if language_code is not None:
            self.language_code = language_code

    def set_author_nick(self, nick: AuthorNick) -> None:
        if self.author_nick is not None:
            raise AuthorNickAlreadySetError(
                "Ник уже задан. Смена возможна через обращение к модератору."
            )
        self.author_nick = nick
        self._emit(AuthorNickSet(user_id=self.id, nick=str(nick)))

    def change_role(self, new_role: Role, *, by_admin_id: UserId) -> None:
        if self.role == new_role:
            return
        old = self.role
        self.role = new_role
        self._emit(
            UserRoleChanged(
                user_id=self.id, old_role=old, new_role=new_role, by_admin_id=by_admin_id
            )
        )

    def ban(self, *, reason: str, by_admin_id: UserId, now: datetime) -> None:
        self.banned_at = now
        self.banned_reason = reason
        self._emit(UserBanned(user_id=self.id, reason=reason, by_admin_id=by_admin_id))

    def unban(self, *, by_admin_id: UserId) -> None:
        self.banned_at = None
        self.banned_reason = None
        self._emit(UserUnbanned(user_id=self.id, by_admin_id=by_admin_id))

    def agree_to_rules(self, *, now: datetime) -> None:
        if self.agreed_at is None:
            self.agreed_at = now

    @property
    def is_banned(self) -> bool:
        return self.banned_at is not None

    @property
    def is_author(self) -> bool:
        return self.author_nick is not None

    @property
    def is_staff(self) -> bool:
        return self.role in (Role.MODERATOR, Role.ADMIN)
