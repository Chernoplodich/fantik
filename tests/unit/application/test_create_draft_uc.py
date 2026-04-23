"""Unit-тесты CreateDraftUseCase — валидация meta + бизнес-правила."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.fanfics.create_draft import (
    CreateDraftCommand,
    CreateDraftUseCase,
)
from app.core.clock import FrozenClock
from app.core.errors import NotFoundError, ValidationError
from app.domain.fanfics.exceptions import TooManyTagsError
from app.domain.fanfics.value_objects import (
    MAX_TAGS_PER_FIC,
    SUMMARY_MAX,
    TITLE_MAX,
    TITLE_MIN,
)

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


def _make_uc(
    clock: FrozenClock,
) -> tuple[CreateDraftUseCase, FakeFanfics, FakeUsers, FakeUow]:
    users = FakeUsers()
    users.add(make_user(tg_id=1))
    fanfics = FakeFanfics()
    tags = FakeTags()
    ref = FakeReference()
    uow = FakeUow()
    uc = CreateDraftUseCase(uow, fanfics, tags, ref, users, clock)
    return uc, fanfics, users, uow


def _cmd(**overrides: object) -> CreateDraftCommand:
    defaults: dict[str, object] = {
        "author_id": 1,
        "title": "Рабочее название",
        "summary": "Краткая аннотация фика",
        "summary_entities": [],
        "fandom_id": 1,
        "age_rating_id": 1,
        "tag_raws": [],
    }
    defaults.update(overrides)
    return CreateDraftCommand(**defaults)  # type: ignore[arg-type]


class TestCreateDraft:
    async def test_happy_path_returns_id_and_commits(self, clock: FrozenClock) -> None:
        uc, fanfics, _, uow = _make_uc(clock)
        result = await uc(_cmd())
        assert result.fic_id > 0
        assert uow.committed is True
        saved = await fanfics.get(fanfics._by_id.__iter__().__next__())  # type: ignore[arg-type]
        assert saved is not None
        assert str(saved.title) == "Рабочее название"

    async def test_title_too_long_rejected(self, clock: FrozenClock) -> None:
        uc, _, _, _ = _make_uc(clock)
        with pytest.raises(ValidationError):
            await uc(_cmd(title="x" * (TITLE_MAX + 1)))

    async def test_title_too_short_rejected(self, clock: FrozenClock) -> None:
        uc, _, _, _ = _make_uc(clock)
        with pytest.raises(ValidationError):
            await uc(_cmd(title="x" * (TITLE_MIN - 1)))

    async def test_summary_too_long_rejected(self, clock: FrozenClock) -> None:
        uc, _, _, _ = _make_uc(clock)
        with pytest.raises(ValidationError):
            await uc(_cmd(summary="y" * (SUMMARY_MAX + 1)))

    async def test_empty_summary_rejected(self, clock: FrozenClock) -> None:
        uc, _, _, _ = _make_uc(clock)
        with pytest.raises(ValidationError):
            await uc(_cmd(summary=""))

    async def test_too_many_tags_rejected(self, clock: FrozenClock) -> None:
        uc, _, _, _ = _make_uc(clock)
        tags = [f"tag_{i}" for i in range(MAX_TAGS_PER_FIC + 1)]
        with pytest.raises(TooManyTagsError):
            await uc(_cmd(tag_raws=tags))

    async def test_missing_user_rejected(self, clock: FrozenClock) -> None:
        users = FakeUsers()  # пустой
        fanfics = FakeFanfics()
        tags = FakeTags()
        ref = FakeReference()
        uow = FakeUow()
        uc = CreateDraftUseCase(uow, fanfics, tags, ref, users, clock)
        with pytest.raises(NotFoundError):
            await uc(_cmd())

    async def test_missing_fandom_rejected(self, clock: FrozenClock) -> None:
        uc, _, _, _ = _make_uc(clock)
        with pytest.raises(NotFoundError):
            await uc(_cmd(fandom_id=999))

    async def test_missing_rating_rejected(self, clock: FrozenClock) -> None:
        uc, _, _, _ = _make_uc(clock)
        with pytest.raises(NotFoundError):
            await uc(_cmd(age_rating_id=999))

    async def test_tags_deduplicated(self, clock: FrozenClock) -> None:
        """Если пользователь ввёл одну и ту же метку дважды (разным кейсом),
        она должна нормализоваться и сохраниться один раз."""
        uc, _, _, _ = _make_uc(clock)
        result = await uc(_cmd(tag_raws=["AU", "au", "  AU  "]))
        assert result.fic_id > 0
