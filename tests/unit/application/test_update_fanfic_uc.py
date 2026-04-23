"""Unit-тесты UpdateFanficUseCase — валидация полей и бизнес-правила статусов."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.fanfics.create_draft import (
    CreateDraftCommand,
    CreateDraftUseCase,
)
from app.application.fanfics.update_fanfic import (
    UpdateFanficCommand,
    UpdateFanficUseCase,
)
from app.core.clock import FrozenClock
from app.core.errors import NotFoundError, ValidationError
from app.domain.fanfics.exceptions import ForbiddenActionError, WrongStatusError
from app.domain.fanfics.value_objects import TITLE_MAX, FicStatus
from app.domain.shared.types import FanficId

from ._fakes import (
    FakeFanfics,
    FakeReference,
    FakeTags,
    FakeUow,
    FakeUsers,
    make_user,
)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC))


async def _seed_fic(
    clock: FrozenClock,
    *,
    author_id: int = 1,
) -> tuple[int, FakeFanfics, FakeReference, FakeTags]:
    users = FakeUsers()
    users.add(make_user(tg_id=author_id))
    fanfics = FakeFanfics()
    tags = FakeTags()
    ref = FakeReference()
    uow = FakeUow()
    create = CreateDraftUseCase(uow, fanfics, tags, ref, users, clock)
    result = await create(
        CreateDraftCommand(
            author_id=author_id,
            title="Тест",
            summary="Аннотация",
            summary_entities=[],
            fandom_id=1,
            age_rating_id=1,
            tag_raws=[],
        )
    )
    return result.fic_id, fanfics, ref, tags


class TestUpdateFanfic:
    async def test_happy_edit(self, clock: FrozenClock) -> None:
        fic_id, fanfics, ref, tags = await _seed_fic(clock)
        uc = UpdateFanficUseCase(FakeUow(), fanfics, tags, ref, clock)
        await uc(
            UpdateFanficCommand(
                fic_id=fic_id,
                author_id=1,
                title="Новый заголовок",
                summary="Новая аннотация",
                summary_entities=[],
                fandom_id=1,
                age_rating_id=1,
                tag_raws=["au"],
            )
        )
        fic = await fanfics.get(FanficId(fic_id))
        assert fic is not None
        assert str(fic.title) == "Новый заголовок"
        assert str(fic.summary) == "Новая аннотация"

    async def test_forbidden_for_wrong_author(self, clock: FrozenClock) -> None:
        fic_id, fanfics, ref, tags = await _seed_fic(clock, author_id=1)
        uc = UpdateFanficUseCase(FakeUow(), fanfics, tags, ref, clock)
        with pytest.raises(ForbiddenActionError):
            await uc(
                UpdateFanficCommand(
                    fic_id=fic_id,
                    author_id=999,
                    title="Ок заголовок",
                    summary="Валидная аннотация",
                    summary_entities=[],
                    fandom_id=1,
                    age_rating_id=1,
                    tag_raws=[],
                )
            )

    async def test_title_too_long_rejected(self, clock: FrozenClock) -> None:
        fic_id, fanfics, ref, tags = await _seed_fic(clock)
        uc = UpdateFanficUseCase(FakeUow(), fanfics, tags, ref, clock)
        with pytest.raises(ValidationError):
            await uc(
                UpdateFanficCommand(
                    fic_id=fic_id,
                    author_id=1,
                    title="x" * (TITLE_MAX + 1),
                    summary="A",
                    summary_entities=[],
                    fandom_id=1,
                    age_rating_id=1,
                    tag_raws=[],
                )
            )

    async def test_cannot_edit_approved_fic(self, clock: FrozenClock) -> None:
        """Approved-фик редактируется ТОЛЬКО через submit → approve-цикл."""
        fic_id, fanfics, ref, tags = await _seed_fic(clock)
        fic = await fanfics.get(FanficId(fic_id))
        assert fic is not None
        fic.status = FicStatus.APPROVED
        await fanfics.save(fic)

        uc = UpdateFanficUseCase(FakeUow(), fanfics, tags, ref, clock)
        with pytest.raises(WrongStatusError):
            await uc(
                UpdateFanficCommand(
                    fic_id=fic_id,
                    author_id=1,
                    title="Новое название",
                    summary="Новая аннотация",
                    summary_entities=[],
                    fandom_id=1,
                    age_rating_id=1,
                    tag_raws=[],
                )
            )

    async def test_missing_fic_rejected(self, clock: FrozenClock) -> None:
        _, fanfics, ref, tags = await _seed_fic(clock)
        uc = UpdateFanficUseCase(FakeUow(), fanfics, tags, ref, clock)
        with pytest.raises(NotFoundError):
            await uc(
                UpdateFanficCommand(
                    fic_id=9999,
                    author_id=1,
                    title="Ок заголовок",
                    summary="Валидная аннотация",
                    summary_entities=[],
                    fandom_id=1,
                    age_rating_id=1,
                    tag_raws=[],
                )
            )
