"""Integration тест flow: вставить delivery, прогнать deliver_one → status=sent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.application.broadcasts.deliver_one import (
    DeliverOneCommand,
    DeliverOneUseCase,
)
from app.application.broadcasts.ports import CopyOK, CopyResult, IBroadcastBot
from app.core.clock import FrozenClock
from app.domain.broadcasts.entities import Broadcast
from app.domain.broadcasts.value_objects import DeliveryStatus
from app.domain.shared.types import BroadcastId, UserId
from app.infrastructure.db.repositories.broadcasts import (
    BroadcastRepository,
    DeliveryRepository,
)
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


@dataclass
class FakeBot(IBroadcastBot):
    ok_result: CopyResult = field(default_factory=CopyOK)
    calls: int = 0

    async def copy_message(self, **kw: Any) -> CopyResult:
        self.calls += 1
        return self.ok_result

    async def send_text(self, **kw: Any) -> None:
        pass


class FakeBucket:
    async def acquire(self, *a: Any, **kw: Any) -> None:
        pass


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)
class TestDeliverFlow:
    async def test_100_recipients_all_sent(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(
                    text("DELETE FROM broadcast_deliveries WHERE TRUE")
                )
                await setup_conn.execute(text("DELETE FROM broadcasts WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone, role) "
                        "VALUES (7001, 'UTC', 'admin') ON CONFLICT (id) DO NOTHING"
                    )
                )
                # 100 получателей
                for uid in range(7100, 7200):
                    await setup_conn.execute(
                        text(
                            "INSERT INTO users (id, timezone) VALUES (:u, 'UTC') "
                            "ON CONFLICT (id) DO NOTHING"
                        ),
                        {"u": uid},
                    )

            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()
                bc_repo = BroadcastRepository(session)
                d_repo = DeliveryRepository(session)

                now = datetime.now(tz=UTC)
                draft = Broadcast.new_draft(
                    broadcast_id=BroadcastId(0),
                    created_by=UserId(7001),
                    source_chat_id=111,
                    source_message_id=22,
                    now=now,
                )
                draft.set_segment({"kind": "all"})
                bid = await bc_repo.create(draft)
                draft = await bc_repo.get(bid)
                assert draft is not None
                draft.launch(now=now)
                await bc_repo.save(draft)

                user_ids = [UserId(u) for u in range(7100, 7200)]
                await d_repo.upsert_pending(broadcast_id=bid, user_ids=user_ids)

                await session.commit()
                await session.close()

            # Прогоняем deliver_one для каждого — новый session per delivery.
            for uid in user_ids:
                async with engine.connect() as conn:
                    session = AsyncSession(bind=conn, expire_on_commit=False)
                    uow = SqlAlchemyUnitOfWork(session)
                    bc_repo = BroadcastRepository(session)
                    d_repo = DeliveryRepository(session)
                    bot = FakeBot()
                    bucket = FakeBucket()
                    clock = FrozenClock(at=now)
                    uc = DeliverOneUseCase(
                        uow, bc_repo, d_repo, bot, bucket,  # type: ignore[arg-type]
                        s, clock,
                    )
                    res = await uc(
                        DeliverOneCommand(broadcast_id=int(bid), user_id=int(uid))
                    )
                    assert res.sent is True
                    await session.close()

            # Финальная проверка: все 100 sent.
            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                d_repo = DeliveryRepository(session)
                counts = await d_repo.count_by_status(bid)
                assert counts[DeliveryStatus.SENT] == 100
                assert counts[DeliveryStatus.PENDING] == 0
                await session.close()
        finally:
            await engine.dispose()

    async def test_cancelled_broadcast_marks_pending_as_failed(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        try:
            async with engine.begin() as setup_conn:
                await setup_conn.execute(
                    text("DELETE FROM broadcast_deliveries WHERE TRUE")
                )
                await setup_conn.execute(text("DELETE FROM broadcasts WHERE TRUE"))
                await setup_conn.execute(
                    text(
                        "INSERT INTO users (id, timezone, role) "
                        "VALUES (7501, 'UTC', 'admin'), (7502, 'UTC', 'user') "
                        "ON CONFLICT (id) DO NOTHING"
                    )
                )

            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.begin()
                bc_repo = BroadcastRepository(session)
                d_repo = DeliveryRepository(session)

                now = datetime.now(tz=UTC)
                draft = Broadcast.new_draft(
                    broadcast_id=BroadcastId(0),
                    created_by=UserId(7501),
                    source_chat_id=111,
                    source_message_id=22,
                    now=now,
                )
                draft.set_segment({"kind": "all"})
                bid = await bc_repo.create(draft)

                bc = await bc_repo.get(bid)
                assert bc is not None
                bc.launch(now=now)
                await bc_repo.save(bc)
                await d_repo.upsert_pending(
                    broadcast_id=bid, user_ids=[UserId(7502)]
                )

                bc2 = await bc_repo.get(bid)
                assert bc2 is not None
                bc2.cancel(actor_id=UserId(7501), now=now)
                await bc_repo.save(bc2)

                await session.commit()
                await session.close()

            async with engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                uow = SqlAlchemyUnitOfWork(session)
                bc_repo = BroadcastRepository(session)
                d_repo = DeliveryRepository(session)
                bot = FakeBot()
                bucket = FakeBucket()
                clock = FrozenClock(at=datetime.now(tz=UTC))
                uc = DeliverOneUseCase(
                    uow, bc_repo, d_repo, bot, bucket,  # type: ignore[arg-type]
                    s, clock,
                )
                res = await uc(
                    DeliverOneCommand(broadcast_id=int(bid), user_id=7502)
                )
                assert res.sent is False
                assert bot.calls == 0  # не вызываем TG при cancelled
                counts = await d_repo.count_by_status(bid)
                assert counts[DeliveryStatus.FAILED] == 1
                await session.close()
        finally:
            await engine.dispose()
