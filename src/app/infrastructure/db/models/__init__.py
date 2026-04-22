"""Все модели импортируются здесь для Alembic autogenerate."""

from app.infrastructure.db.base import Base  # noqa: F401
from app.infrastructure.db.models.age_rating import AgeRating  # noqa: F401
from app.infrastructure.db.models.audit_log import AuditLog  # noqa: F401
from app.infrastructure.db.models.chapter import Chapter  # noqa: F401
from app.infrastructure.db.models.chapter_page import ChapterPage  # noqa: F401
from app.infrastructure.db.models.fandom import Fandom  # noqa: F401
from app.infrastructure.db.models.fanfic import Fanfic  # noqa: F401
from app.infrastructure.db.models.fanfic_tag import FanficTag  # noqa: F401
from app.infrastructure.db.models.fanfic_version import FanficVersion  # noqa: F401
from app.infrastructure.db.models.moderation_queue import ModerationQueue  # noqa: F401
from app.infrastructure.db.models.moderation_reason import ModerationReason  # noqa: F401
from app.infrastructure.db.models.outbox import Outbox  # noqa: F401
from app.infrastructure.db.models.tag import Tag  # noqa: F401
from app.infrastructure.db.models.tracking import (  # noqa: F401
    TrackingCode,
    TrackingEvent,
)
from app.infrastructure.db.models.user import User  # noqa: F401

__all__ = [
    "AgeRating",
    "AuditLog",
    "Base",
    "Chapter",
    "ChapterPage",
    "Fandom",
    "Fanfic",
    "FanficTag",
    "FanficVersion",
    "ModerationQueue",
    "ModerationReason",
    "Outbox",
    "Tag",
    "TrackingCode",
    "TrackingEvent",
    "User",
]
