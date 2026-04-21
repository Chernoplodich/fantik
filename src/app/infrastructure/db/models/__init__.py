"""Все модели импортируются здесь для Alembic autogenerate."""

from app.infrastructure.db.base import Base  # noqa: F401
from app.infrastructure.db.models.age_rating import AgeRating  # noqa: F401
from app.infrastructure.db.models.fandom import Fandom  # noqa: F401
from app.infrastructure.db.models.tag import Tag  # noqa: F401
from app.infrastructure.db.models.tracking import (  # noqa: F401
    TrackingCode,
    TrackingEvent,
)
from app.infrastructure.db.models.user import User  # noqa: F401

__all__ = [
    "AgeRating",
    "Base",
    "Fandom",
    "Tag",
    "TrackingCode",
    "TrackingEvent",
    "User",
]
