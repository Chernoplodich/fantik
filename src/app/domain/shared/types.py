"""Типобезопасные идентификаторы: NewType вместо голого int."""

from __future__ import annotations

from typing import NewType

UserId = NewType("UserId", int)  # = Telegram tg_id
FanficId = NewType("FanficId", int)
ChapterId = NewType("ChapterId", int)
FandomId = NewType("FandomId", int)
TagId = NewType("TagId", int)
TrackingCodeId = NewType("TrackingCodeId", int)
TrackingEventId = NewType("TrackingEventId", int)
BroadcastId = NewType("BroadcastId", int)
ModerationCaseId = NewType("ModerationCaseId", int)
