"""Доменные события пользователя."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.domain.shared.events import DomainEvent
from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.users.value_objects import Role


@dataclass(frozen=True, kw_only=True)
class UserRegistered(DomainEvent):
    user_id: UserId
    utm_code_id: TrackingCodeId | None
    name: ClassVar[str] = "user.registered"


@dataclass(frozen=True, kw_only=True)
class AuthorNickSet(DomainEvent):
    user_id: UserId
    nick: str
    name: ClassVar[str] = "user.author_nick_set"


@dataclass(frozen=True, kw_only=True)
class UserRoleChanged(DomainEvent):
    user_id: UserId
    old_role: Role
    new_role: Role
    by_admin_id: UserId
    name: ClassVar[str] = "user.role_changed"


@dataclass(frozen=True, kw_only=True)
class UserBanned(DomainEvent):
    user_id: UserId
    reason: str
    by_admin_id: UserId
    name: ClassVar[str] = "user.banned"


@dataclass(frozen=True, kw_only=True)
class UserUnbanned(DomainEvent):
    user_id: UserId
    by_admin_id: UserId
    name: ClassVar[str] = "user.unbanned"
