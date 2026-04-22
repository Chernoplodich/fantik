"""Value-объекты и константы домена модерации."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from app.domain.shared.types import ModerationReasonId

LOCK_DURATION = timedelta(minutes=15)
REJECT_COMMENT_MAX = 2000


class ReasonCode(StrEnum):
    RATING_MISMATCH = "RATING_MISMATCH"
    PLAGIARISM = "PLAGIARISM"
    LOW_QUALITY = "LOW_QUALITY"
    NO_FANDOM = "NO_FANDOM"
    INVALID_FORMAT = "INVALID_FORMAT"
    WRONG_TAGS = "WRONG_TAGS"
    RULES_VIOLATION = "RULES_VIOLATION"


@dataclass(frozen=True, kw_only=True)
class RejectionReason:
    id: ModerationReasonId
    code: ReasonCode
    title: str
    description: str
    sort_order: int
    active: bool
