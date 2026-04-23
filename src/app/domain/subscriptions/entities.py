"""Подписка: read-model для связи (subscriber_id, author_id).

Доменная сущность максимально простая — это фактически кортеж двух ссылок
и момент создания. Всё поведение (idempotent add, анти-самоподписка) живёт
в use case'ах / репозитории.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.shared.types import UserId


@dataclass(frozen=True, kw_only=True)
class Subscription:
    subscriber_id: UserId
    author_id: UserId
    created_at: datetime
