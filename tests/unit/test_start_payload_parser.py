"""Тест парсера аргумента /start в роутере start.py."""

from __future__ import annotations

import pytest

from app.presentation.bot.routers.start import _parse_payload


class TestParsePayload:
    def test_empty(self) -> None:
        assert _parse_payload("") == (None, None)
        assert _parse_payload("   ") == (None, None)

    @pytest.mark.parametrize("code", ["abc12345", "A1b2C3d4", "XYZ89012"])
    def test_utm_code(self, code: str) -> None:
        assert _parse_payload(code) == (code, None)

    @pytest.mark.parametrize("bad", ["abc-12345", "too_short", "x" * 17, "fic__42"])
    def test_invalid_returns_none(self, bad: str) -> None:
        assert _parse_payload(bad) == (None, None)

    @pytest.mark.parametrize("fic, expected", [("fic_42", "fic_42"), ("fic_1", "fic_1")])
    def test_fic_deeplink(self, fic: str, expected: str) -> None:
        assert _parse_payload(fic) == (None, expected)
