"""Тесты валидации AuthorNick."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.domain.users.value_objects import AuthorNick


class TestAuthorNickValidation:
    def test_accepts_alnum_underscore_dash(self) -> None:
        nick = AuthorNick("mark_the_writer-42")
        assert str(nick) == "mark_the_writer-42"
        assert nick.lowered == "mark_the_writer-42"

    def test_strips_whitespace(self) -> None:
        assert str(AuthorNick("  bob  ")) == "bob"

    @pytest.mark.parametrize(
        "bad",
        ["", "a", "a" * 33, "bob smith", "имя_по_русски", "bob.smith", "x@y", "user!"],
    )
    def test_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            AuthorNick(bad)

    def test_preserves_case_but_lowered_returns_lower(self) -> None:
        nick = AuthorNick("MarkTheWriter")
        assert str(nick) == "MarkTheWriter"
        assert nick.lowered == "markthewriter"
