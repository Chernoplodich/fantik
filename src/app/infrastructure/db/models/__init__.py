"""Все модели импортируются здесь для Alembic autogenerate."""

from app.infrastructure.db.base import Base
from app.infrastructure.db.models.age_rating import AgeRating
from app.infrastructure.db.models.audit_log import AuditLog
from app.infrastructure.db.models.bookmark import Bookmark
from app.infrastructure.db.models.chapter import Chapter
from app.infrastructure.db.models.chapter_page import ChapterPage
from app.infrastructure.db.models.fandom import Fandom
from app.infrastructure.db.models.fanfic import Fanfic
from app.infrastructure.db.models.fanfic_tag import FanficTag
from app.infrastructure.db.models.fanfic_version import FanficVersion
from app.infrastructure.db.models.like import Like
from app.infrastructure.db.models.moderation_queue import ModerationQueue
from app.infrastructure.db.models.moderation_reason import ModerationReason
from app.infrastructure.db.models.outbox import Outbox
from app.infrastructure.db.models.read_completed import ReadCompleted
from app.infrastructure.db.models.reading_progress import ReadingProgress
from app.infrastructure.db.models.tag import Tag
from app.infrastructure.db.models.tracking import (
    TrackingCode,
    TrackingEvent,
)
from app.infrastructure.db.models.user import User

__all__ = [
    "AgeRating",
    "AuditLog",
    "Base",
    "Bookmark",
    "Chapter",
    "ChapterPage",
    "Fandom",
    "Fanfic",
    "FanficTag",
    "FanficVersion",
    "Like",
    "ModerationQueue",
    "ModerationReason",
    "Outbox",
    "ReadCompleted",
    "ReadingProgress",
    "Tag",
    "TrackingCode",
    "TrackingEvent",
    "User",
]
