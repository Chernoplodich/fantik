"""Unit-тесты DeliverOneUseCase: классификация ошибок copy_message."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

import pytest

from app.application.broadcasts.deliver_one import (
    DeliverOneCommand,
    DeliverOneUseCase,
    DeliveryRetryRequestedError,
)
from app.application.broadcasts.ports import (
    CopyBadRequest,
    CopyBlocked,
    CopyOK,
    CopyResult,
    CopyRetryAfter,
    Delivery,
    IBroadcastBot,
    IBroadcastRepository,
    IDeliveryRepository,
)
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.domain.broadcasts.entities import Broadcast
from app.domain.broadcasts.value_objects import BroadcastStatus, DeliveryStatus
from app.domain.shared.types import BroadcastId, UserId

_NOW = datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC)


class FakeUow:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *a: object) -> None:
        return None

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    def record_events(self, events: list[object]) -> None: ...
    def collect_events(self) -> list[object]:
        return []


@dataclass
class FakeBroadcastRepo(IBroadcastRepository):
    bc: Broadcast

    async def create(self, broadcast: Broadcast) -> BroadcastId:
        raise NotImplementedError

    async def get(self, broadcast_id: BroadcastId) -> Broadcast | None:
        return self.bc if int(broadcast_id) == int(self.bc.id) else None

    async def save(self, broadcast: Broadcast) -> None:
        self.bc = broadcast

    async def list_by_creator(self, *, created_by, limit=20):  # type: ignore[no-untyped-def]
        return []

    async def list_by_status(self, statuses, limit=100):  # type: ignore[no-untyped-def]
        return []

    async def scan_ready_to_run(self, *, now, limit=10):  # type: ignore[no-untyped-def]
        return []

    async def update_stats(self, *, broadcast_id, stats) -> None:  # type: ignore[no-untyped-def]
        pass


@dataclass
class FakeDeliveryRepo(IDeliveryRepository):
    delivery: Delivery

    async def upsert_pending(self, *, broadcast_id, user_ids) -> int:  # type: ignore[no-untyped-def]
        return 0

    async def get_for_update(self, *, broadcast_id, user_id):  # type: ignore[no-untyped-def]
        if int(broadcast_id) == int(self.delivery.broadcast_id) and int(user_id) == int(
            self.delivery.user_id
        ):
            return self.delivery
        return None

    async def save(self, delivery: Delivery) -> None:
        self.delivery = delivery

    async def count_by_status(self, broadcast_id):  # type: ignore[no-untyped-def]
        return {}

    async def iter_user_ids_by_status(self, **kw: Any) -> AsyncIterator[list[UserId]]:
        if False:  # pragma: no cover
            yield []
        return


@dataclass
class FakeBot(IBroadcastBot):
    result_queue: list[CopyResult] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def copy_message(
        self,
        *,
        chat_id: int,
        from_chat_id: int,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
        allow_paid_broadcast: bool = False,
        protect_content: bool = False,
    ) -> CopyResult:
        self.calls.append(
            {
                "chat_id": chat_id,
                "from_chat_id": from_chat_id,
                "message_id": message_id,
                "reply_markup": reply_markup,
                "allow_paid_broadcast": allow_paid_broadcast,
            }
        )
        return self.result_queue.pop(0)

    async def send_text(self, *, chat_id: int, text: str) -> None:
        pass


class FakeBucket:
    def __init__(self) -> None:
        self.acquired: list[tuple[str, float, int]] = []

    async def acquire(self, key: str, rate: float, capacity: int) -> None:
        self.acquired.append((key, rate, capacity))


def _make_broadcast(
    status: BroadcastStatus = BroadcastStatus.RUNNING,
) -> Broadcast:
    return Broadcast(
        id=BroadcastId(1),
        created_by=UserId(1),
        source_chat_id=100,
        source_message_id=50,
        status=status,
        segment_spec={"kind": "all"},
    )


def _make_delivery(status: DeliveryStatus = DeliveryStatus.PENDING, attempts: int = 0) -> Delivery:
    return Delivery(
        broadcast_id=BroadcastId(1),
        user_id=UserId(200),
        status=status,
        attempts=attempts,
        error_code=None,
        sent_at=None,
    )


class FakeUsersRepo:
    def __init__(self) -> None:
        self.blocked: list[int] = []
        self.cleared: list[int] = []

    async def mark_bot_blocked(self, user_id) -> None:  # type: ignore[no-untyped-def]
        self.blocked.append(int(user_id))

    async def clear_bot_blocked(self, user_id) -> None:  # type: ignore[no-untyped-def]
        self.cleared.append(int(user_id))


def _uc(
    bc: Broadcast,
    delivery: Delivery,
    results: list[CopyResult],
    *,
    allow_paid: bool = False,
) -> tuple[DeliverOneUseCase, FakeBot, FakeDeliveryRepo, FakeUsersRepo]:
    broadcasts = FakeBroadcastRepo(bc=bc)
    deliveries = FakeDeliveryRepo(delivery=delivery)
    users = FakeUsersRepo()
    bot = FakeBot(result_queue=list(results))
    bucket = FakeBucket()
    settings = Settings(
        bot_token="0:fake",
        meili_master_key="meili-master-key-enough-len-for-check",
        allow_paid_broadcast=allow_paid,
    )
    clock = FrozenClock(at=_NOW)
    uc = DeliverOneUseCase(
        uow=FakeUow(),
        broadcasts=broadcasts,
        deliveries=deliveries,
        users=users,  # type: ignore[arg-type]
        bot=bot,
        bucket=bucket,  # type: ignore[arg-type]
        settings=settings,
        clock=clock,
    )
    return uc, bot, deliveries, users


@pytest.mark.asyncio
async def test_copy_ok_marks_sent() -> None:
    uc, _, deliveries, _users = _uc(_make_broadcast(), _make_delivery(), [CopyOK()])
    res = await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert res.sent is True
    assert res.status == DeliveryStatus.SENT
    assert deliveries.delivery.status == DeliveryStatus.SENT
    assert deliveries.delivery.sent_at is not None


@pytest.mark.asyncio
async def test_forbidden_marks_blocked() -> None:
    uc, _, deliveries, users = _uc(_make_broadcast(), _make_delivery(), [CopyBlocked()])
    res = await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert res.sent is False
    assert deliveries.delivery.status == DeliveryStatus.BLOCKED
    assert deliveries.delivery.error_code == "blocked"
    # Юзер должен быть помечен как заблокировавший бота — чтобы
    # сегмент-резолвер не брал его в следующих рассылках.
    assert users.blocked == [200]


@pytest.mark.asyncio
async def test_retry_after_raises_retry_immediate() -> None:
    uc, _, _, _ = _uc(_make_broadcast(), _make_delivery(), [CopyRetryAfter(seconds=5.0)])
    with pytest.raises(DeliveryRetryRequestedError) as exc_info:
        await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert exc_info.value.increment_attempts is False
    assert exc_info.value.delay_seconds >= 5.0


@pytest.mark.asyncio
async def test_bad_request_increments_attempts_retries() -> None:
    uc, _, deliveries, _users = _uc(
        _make_broadcast(),
        _make_delivery(attempts=0),
        [CopyBadRequest(error_code="some error")],
    )
    with pytest.raises(DeliveryRetryRequestedError) as exc_info:
        await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert exc_info.value.increment_attempts is True
    assert deliveries.delivery.attempts == 1


@pytest.mark.asyncio
async def test_bad_request_exhausted_marks_failed() -> None:
    uc, _, deliveries, _users = _uc(
        _make_broadcast(),
        _make_delivery(attempts=2),  # max_attempts=3, 2+1=3 → failed
        [CopyBadRequest(error_code="final")],
    )
    res = await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert res.sent is False
    assert res.status == DeliveryStatus.FAILED
    assert deliveries.delivery.status == DeliveryStatus.FAILED
    assert deliveries.delivery.attempts == 3


@pytest.mark.asyncio
async def test_already_sent_is_noop() -> None:
    uc, bot, deliveries, _users = _uc(
        _make_broadcast(),
        _make_delivery(status=DeliveryStatus.SENT),
        [CopyOK()],
    )
    res = await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert res.sent is False
    assert res.status == DeliveryStatus.SENT
    assert bot.calls == []  # bot не вызывался


@pytest.mark.asyncio
async def test_cancelled_broadcast_marks_failed_cancelled() -> None:
    uc, bot, deliveries, _users = _uc(
        _make_broadcast(status=BroadcastStatus.CANCELLED),
        _make_delivery(),
        [CopyOK()],
    )
    res = await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert res.sent is False
    assert deliveries.delivery.status == DeliveryStatus.FAILED
    assert deliveries.delivery.error_code == "cancelled"
    assert bot.calls == []


@pytest.mark.asyncio
async def test_allow_paid_broadcast_uses_paid_rate() -> None:
    uc, bot, _, _users = _uc(_make_broadcast(), _make_delivery(), [CopyOK()], allow_paid=True)
    await uc(DeliverOneCommand(broadcast_id=1, user_id=200))
    assert bot.calls[0]["allow_paid_broadcast"] is True
