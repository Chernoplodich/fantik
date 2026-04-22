"""Unit-тесты tag_normalizer."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.domain.fanfics.services import tag_normalizer


class TestTagNormalizer:
    def test_ascii_name(self) -> None:
        name, slug = tag_normalizer.normalize("Sherlock Holmes")
        assert str(name) == "Sherlock Holmes"
        assert str(slug) == "sherlock-holmes"

    def test_cyrillic_transliteration(self) -> None:
        name, slug = tag_normalizer.normalize("  АнГст  ")
        assert str(name) == "АнГст"
        assert str(slug) == "angst"

    def test_trims_and_collapses_spaces(self) -> None:
        name, slug = tag_normalizer.normalize("a  b   c")
        assert str(name) == "a b c"
        assert str(slug) == "a-b-c"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            tag_normalizer.normalize(" ")

    def test_only_non_ascii_raises(self) -> None:
        # одни диакритики / иероглифы — слага нет
        with pytest.raises(ValidationError):
            tag_normalizer.normalize("漢字漢字")

    def test_mixed_keeps_cyr_in_name(self) -> None:
        name, slug = tag_normalizer.normalize("Тёмные Искусства")
        # ё → e в слаге
        assert "t" in str(slug)
        assert "mn" in str(slug) or "m" in str(slug)
        assert str(name) == "Тёмные Искусства"
