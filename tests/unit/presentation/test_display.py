"""UI-утилита `display_author_nick`: подмена `deleted_*` на человекочитаемое."""

from __future__ import annotations

from app.presentation.bot.display import (
    DELETED_USER_LABEL,
    display_author_nick,
    is_anonymized_nick,
)


def test_none_passes_through() -> None:
    assert display_author_nick(None) is None


def test_regular_nick_unchanged() -> None:
    assert display_author_nick("ivan") == "ivan"


def test_anonymized_maps_to_label() -> None:
    assert display_author_nick("deleted_abcdef12") == DELETED_USER_LABEL
    assert is_anonymized_nick("deleted_abcdef12")


def test_non_anonymized_prefix() -> None:
    # Обычный ник, начинающийся с «delete» — НЕ анонимизирован.
    assert display_author_nick("deletion_expert") == "deletion_expert"
