"""Value objects для жалоб."""

from __future__ import annotations

from enum import StrEnum


class ReportTarget(StrEnum):
    FANFIC = "fanfic"
    CHAPTER = "chapter"
    USER = "user"
    COMMENT = "comment"  # задел на пост-MVP


class ReportStatus(StrEnum):
    OPEN = "open"
    DISMISSED = "dismissed"
    ACTIONED = "actioned"


class ReportDecision(StrEnum):
    """Решение модератора по жалобе."""

    DISMISS = "dismiss"
    ACTION = "action"


# Коды причин из UI-пикера. Денормализованы в reports.reason_code (TEXT), а не
# через FK — у жалоб свой набор причин, отличный от moderation_reasons (которые
# для отказа в публикации). Активные коды добавляй сюда.
REPORT_REASON_CODES: tuple[str, ...] = (
    "SPAM",
    "NSFW_UNMARKED",
    "PLAGIARISM",
    "HARASSMENT",
    "WRONG_TAGS",
    "OTHER",
)

REPORT_REASON_TITLES: dict[str, str] = {
    "SPAM": "Спам / реклама",
    "NSFW_UNMARKED": "NSFW без рейтинга",
    "PLAGIARISM": "Плагиат",
    "HARASSMENT": "Оскорбления",
    "WRONG_TAGS": "Неверные теги",
    "OTHER": "Другое",
}
