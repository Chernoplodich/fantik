"""Value objects для заявок на фандом."""

from __future__ import annotations

from enum import StrEnum
from typing import NewType

ProposalId = NewType("ProposalId", int)


class FandomProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
