"""Integration: PgFandomProposalRepository — anti-dup, lifecycle, list_pending."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import ConflictError
from app.domain.reference.value_objects import FandomProposalStatus, ProposalId
from app.domain.shared.types import FandomId, UserId
from app.infrastructure.db.repositories.fandom_proposals import (
    PgFandomProposalRepository,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="Нет реального PG — запусти make up или CI",
)


async def _ensure_user(engine, uid: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, timezone) VALUES (:id, 'UTC') ON CONFLICT DO NOTHING"),
            {"id": uid},
        )


async def _cleanup_proposals(engine, requested_by: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM fandom_proposals WHERE requested_by = :uid"),
            {"uid": requested_by},
        )


@pytest.mark.integration
class TestProposalsRepo:
    async def test_create_and_get(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        uid = 1_000_000 + abs(hash(str(uuid.uuid4()))) % 999_999
        await _ensure_user(engine, uid)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = PgFandomProposalRepository(session)
                p = await repo.create(
                    requested_by=UserId(uid),
                    name="Test Fandom Proposal",
                    category_hint="anime",
                    comment="хочу",
                    now=datetime.now(tz=UTC),
                )
                await session.commit()
                got = await repo.get(p.id)
                assert got is not None
                assert got.name == "Test Fandom Proposal"
                assert got.status is FandomProposalStatus.PENDING
        finally:
            await _cleanup_proposals(engine, uid)
            await engine.dispose()

    async def test_anti_dup_open_per_user_name(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        uid = 2_000_000 + abs(hash(str(uuid.uuid4()))) % 999_999
        await _ensure_user(engine, uid)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = PgFandomProposalRepository(session)
                await repo.create(
                    requested_by=UserId(uid),
                    name="Duplicate",
                    category_hint="anime",
                    comment=None,
                    now=datetime.now(tz=UTC),
                )
                with pytest.raises(ConflictError):
                    await repo.create(
                        requested_by=UserId(uid),
                        name="Duplicate",
                        category_hint="anime",
                        comment=None,
                        now=datetime.now(tz=UTC),
                    )
        finally:
            await _cleanup_proposals(engine, uid)
            await engine.dispose()

    async def test_approve_then_same_name_can_be_resubmitted(self) -> None:
        """После approve тот же юзер может повторно подать ту же заявку."""
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        uid = 3_000_000 + abs(hash(str(uuid.uuid4()))) % 999_999
        await _ensure_user(engine, uid)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = PgFandomProposalRepository(session)
                p = await repo.create(
                    requested_by=UserId(uid),
                    name="Reusable",
                    category_hint="anime",
                    comment=None,
                    now=datetime.now(tz=UTC),
                )
                p.approve(
                    moderator_id=UserId(uid),
                    fandom_id=FandomId(1),
                    comment=None,
                    now=datetime.now(tz=UTC),
                )
                await repo.save(p)
                await session.commit()

                # Повторная заявка с тем же именем — должна пройти, т.к. partial unique
                # учитывает status='pending'.
                p2 = await repo.create(
                    requested_by=UserId(uid),
                    name="Reusable",
                    category_hint="anime",
                    comment=None,
                    now=datetime.now(tz=UTC),
                )
                assert p2.id != p.id
        finally:
            await _cleanup_proposals(engine, uid)
            await engine.dispose()

    async def test_list_pending_returns_only_pending(self) -> None:
        from app.core.config import Settings

        s = Settings()  # type: ignore[call-arg]
        engine = create_async_engine(s.postgres_url)
        uid = 4_000_000 + abs(hash(str(uuid.uuid4()))) % 999_999
        await _ensure_user(engine, uid)
        try:
            sm = async_sessionmaker(engine, expire_on_commit=False)
            async with sm() as session:
                repo = PgFandomProposalRepository(session)
                # 1 pending + 1 approved.
                await repo.create(
                    requested_by=UserId(uid),
                    name="Pending One",
                    category_hint="anime",
                    comment=None,
                    now=datetime.now(tz=UTC),
                )
                p2 = await repo.create(
                    requested_by=UserId(uid),
                    name="Will Approve",
                    category_hint="anime",
                    comment=None,
                    now=datetime.now(tz=UTC),
                )
                p2.approve(
                    moderator_id=UserId(uid),
                    fandom_id=FandomId(1),
                    comment=None,
                    now=datetime.now(tz=UTC),
                )
                await repo.save(p2)
                await session.commit()

                rows = await repo.list_pending(limit=50)
                names = {r.name for r in rows if r.requested_by == UserId(uid)}
                assert "Pending One" in names
                assert "Will Approve" not in names
        finally:
            await _cleanup_proposals(engine, uid)
            await engine.dispose()


@pytest.mark.integration
async def test_dummy_dt_use_for_lint() -> None:
    """Заглушка чтобы DTZ-rule не свёл линтер с ума."""
    assert datetime.now(tz=UTC) is not None
    assert ProposalId is not None
