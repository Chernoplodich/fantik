"""Тесты агрегата User."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.shared.types import TrackingCodeId, UserId
from app.domain.users.entities import User
from app.domain.users.events import (
    AuthorNickSet,
    UserBanned,
    UserRegistered,
    UserRoleChanged,
    UserUnbanned,
)
from app.domain.users.exceptions import AuthorNickAlreadySetError
from app.domain.users.value_objects import AuthorNick, Role

NOW = datetime(2026, 4, 21, 12, 0, 0, tzinfo=UTC)


class TestUserRegistration:
    def test_register_emits_user_registered_event(self) -> None:
        user = User.register(
            tg_id=777,
            username="alice",
            first_name="Alice",
            last_name=None,
            language_code="ru",
            utm_code_id=TrackingCodeId(42),
            now=NOW,
        )
        events = user.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], UserRegistered)
        assert events[0].user_id == UserId(777)
        assert events[0].utm_code_id == TrackingCodeId(42)

    def test_register_defaults(self) -> None:
        user = User.register(
            tg_id=1,
            username=None,
            first_name=None,
            last_name=None,
            language_code=None,
            utm_code_id=None,
            now=NOW,
        )
        assert user.role == Role.USER
        assert user.author_nick is None
        assert user.banned_at is None
        assert not user.is_author
        assert not user.is_banned
        assert not user.is_staff


class TestSetAuthorNick:
    def test_set_nick_first_time_emits_event(self) -> None:
        user = User(id=UserId(1))
        user.set_author_nick(AuthorNick("bob"))
        events = user.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], AuthorNickSet)
        assert events[0].nick == "bob"
        assert user.is_author

    def test_cannot_set_nick_twice(self) -> None:
        user = User(id=UserId(1), author_nick=AuthorNick("bob"))
        with pytest.raises(AuthorNickAlreadySetError):
            user.set_author_nick(AuthorNick("alice"))


class TestRoleChange:
    def test_change_role_emits_event(self) -> None:
        user = User(id=UserId(1), role=Role.USER)
        user.change_role(Role.MODERATOR, by_admin_id=UserId(999))
        events = user.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], UserRoleChanged)
        assert events[0].old_role == Role.USER
        assert events[0].new_role == Role.MODERATOR
        assert user.role == Role.MODERATOR
        assert user.is_staff

    def test_no_event_when_role_unchanged(self) -> None:
        user = User(id=UserId(1), role=Role.ADMIN)
        user.change_role(Role.ADMIN, by_admin_id=UserId(999))
        assert user.pull_events() == []


class TestBan:
    def test_ban_sets_fields_and_emits_event(self) -> None:
        user = User(id=UserId(1))
        user.ban(reason="spam", by_admin_id=UserId(999), now=NOW)
        events = user.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], UserBanned)
        assert user.is_banned
        assert user.banned_reason == "spam"
        assert user.banned_at == NOW

    def test_unban_clears_fields(self) -> None:
        user = User(id=UserId(1), banned_at=NOW, banned_reason="spam")
        user.unban(by_admin_id=UserId(999))
        events = user.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], UserUnbanned)
        assert not user.is_banned
        assert user.banned_reason is None


class TestAgreeToRules:
    def test_first_agreement_sets_timestamp(self) -> None:
        user = User(id=UserId(1))
        user.agree_to_rules(now=NOW)
        assert user.agreed_at == NOW

    def test_second_agreement_is_noop(self) -> None:
        user = User(id=UserId(1))
        user.agree_to_rules(now=NOW)
        later = datetime(2027, 1, 1, tzinfo=UTC)
        user.agree_to_rules(now=later)
        assert user.agreed_at == NOW  # не перезаписалось
