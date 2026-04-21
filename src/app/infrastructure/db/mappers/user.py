"""Маппер доменной User ↔ ORM User."""

from __future__ import annotations

from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.users.entities import User as UserEntity
from app.domain.users.value_objects import AuthorNick, Role
from app.infrastructure.db.models.user import User as UserModel


def to_domain(m: UserModel) -> UserEntity:
    return UserEntity(
        id=UserId(m.id),
        username=m.username,
        first_name=m.first_name,
        last_name=m.last_name,
        language_code=m.language_code,
        timezone=m.timezone,
        role=Role(m.role),
        author_nick=AuthorNick(m.author_nick) if m.author_nick else None,
        utm_source_code_id=(
            TrackingCodeId(m.utm_source_code_id)
            if m.utm_source_code_id is not None
            else None
        ),
        agreed_at=m.agreed_at,
        banned_at=m.banned_at,
        banned_reason=m.banned_reason,
        created_at=m.created_at,
        last_seen_at=m.last_seen_at,
    )


def apply_to_model(m: UserModel, e: UserEntity) -> None:
    """Обновить поля ORM-модели из доменной сущности (для save())."""
    m.username = e.username
    m.first_name = e.first_name
    m.last_name = e.last_name
    m.language_code = e.language_code
    m.timezone = e.timezone
    m.role = e.role
    m.author_nick = str(e.author_nick) if e.author_nick else None
    m.utm_source_code_id = int(e.utm_source_code_id) if e.utm_source_code_id else None
    m.agreed_at = e.agreed_at
    m.banned_at = e.banned_at
    m.banned_reason = e.banned_reason
    if e.last_seen_at is not None:
        m.last_seen_at = e.last_seen_at


def new_model_from_domain(e: UserEntity) -> UserModel:
    return UserModel(
        id=int(e.id),
        username=e.username,
        first_name=e.first_name,
        last_name=e.last_name,
        language_code=e.language_code,
        timezone=e.timezone,
        role=e.role,
        author_nick=str(e.author_nick) if e.author_nick else None,
        utm_source_code_id=int(e.utm_source_code_id) if e.utm_source_code_id else None,
        agreed_at=e.agreed_at,
        banned_at=e.banned_at,
        banned_reason=e.banned_reason,
        created_at=e.created_at,
        last_seen_at=e.last_seen_at,
    )
