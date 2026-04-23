"""Unit-тесты parse_keyboard_text."""

from __future__ import annotations

import pytest

from app.application.broadcasts.set_keyboard import parse_keyboard_text
from app.domain.broadcasts.exceptions import KeyboardValidationError


def test_single_button_row() -> None:
    kb = parse_keyboard_text("Читать|https://example.com")
    assert kb == [[{"text": "Читать", "url": "https://example.com"}]]


def test_multiple_rows_with_empty_separator() -> None:
    raw = "A|https://a\nB|https://b\n\nC|https://c"
    kb = parse_keyboard_text(raw)
    assert len(kb) == 2
    assert len(kb[0]) == 2  # A, B
    assert len(kb[1]) == 1  # C


def test_tg_scheme_allowed() -> None:
    kb = parse_keyboard_text("Чат|tg://resolve?domain=test")
    assert kb is not None
    assert kb[0][0]["url"].startswith("tg://")


def test_empty_raises() -> None:
    assert parse_keyboard_text("") is None


def test_missing_separator_raises() -> None:
    with pytest.raises(KeyboardValidationError):
        parse_keyboard_text("just text without pipe")


def test_empty_text_raises() -> None:
    with pytest.raises(KeyboardValidationError):
        parse_keyboard_text("|https://example.com")


def test_bad_scheme_raises() -> None:
    with pytest.raises(KeyboardValidationError):
        parse_keyboard_text("x|ftp://files.example.com/foo")


def test_text_too_long_raises() -> None:
    text = "X" * 100
    with pytest.raises(KeyboardValidationError):
        parse_keyboard_text(f"{text}|https://example.com")
