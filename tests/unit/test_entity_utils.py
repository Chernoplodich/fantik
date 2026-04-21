"""Тесты UTF-16 утилит: критично для паджинатора фанфиков."""

from __future__ import annotations

import pytest

from app.infrastructure.telegram.entity_utils import (
    EntityDict,
    char_to_utf16,
    normalize_entities,
    utf16_length,
    utf16_to_char,
    utf16_units_of_char,
)


class TestUtf16Length:
    @pytest.mark.parametrize(
        "s, expected",
        [
            ("", 0),
            ("a", 1),
            ("abc", 3),
            ("Привет", 6),
            ("😀", 2),  # surrogate pair
            ("a😀b", 4),
            ("👨‍👩‍👧", 8),  # ZWJ-последовательность: 3 emoji + 2 ZWJ; ZWJ = 1 unit
        ],
    )
    def test_lengths(self, s: str, expected: int) -> None:
        assert utf16_length(s) == expected


class TestUnitsOfChar:
    def test_bmp_is_one_unit(self) -> None:
        assert utf16_units_of_char("a") == 1
        assert utf16_units_of_char("щ") == 1

    def test_surrogate_is_two_units(self) -> None:
        assert utf16_units_of_char("😀") == 2


class TestCharToUtf16:
    def test_monotonic_on_plain(self) -> None:
        s = "hello"
        for i in range(len(s) + 1):
            assert char_to_utf16(s, i) == i

    def test_with_emoji(self) -> None:
        s = "a😀b"
        assert char_to_utf16(s, 0) == 0
        assert char_to_utf16(s, 1) == 1
        assert char_to_utf16(s, 2) == 3  # после emoji, который занимает 2 units
        assert char_to_utf16(s, 3) == 4


class TestUtf16ToChar:
    def test_roundtrip(self) -> None:
        s = "a😀b😎c"
        for i in range(len(s) + 1):
            u = char_to_utf16(s, i)
            assert utf16_to_char(s, u) == i

    def test_midsurrogate_rounds_down(self) -> None:
        s = "a😀b"  # "a" = 1, "😀" = 2 units, "b" = 1 → общая длина 4
        # позиция 2 = середина emoji → округляем к началу emoji (code point 1)
        assert utf16_to_char(s, 2) == 1


class TestNormalizeEntities:
    def test_none_returns_empty(self) -> None:
        assert normalize_entities(None) == []
        assert normalize_entities([]) == []

    def test_drops_malformed(self) -> None:
        out = normalize_entities(
            [
                {"type": "bold", "offset": 0, "length": 5},
                {"offset": 10, "length": 3},  # без type — выкидываем
                {"type": "italic", "offset": "x", "length": 3},  # невалидные offset
            ]
        )
        assert len(out) == 1
        assert out[0].type == "bold"

    def test_sorted_by_offset(self) -> None:
        out = normalize_entities(
            [
                {"type": "italic", "offset": 10, "length": 3},
                {"type": "bold", "offset": 0, "length": 5},
            ]
        )
        assert [e.offset for e in out] == [0, 10]

    def test_preserves_extra_fields(self) -> None:
        out = normalize_entities(
            [
                {
                    "type": "custom_emoji",
                    "offset": 0,
                    "length": 2,
                    "custom_emoji_id": "abc123",
                }
            ]
        )
        assert out[0].extra == {"custom_emoji_id": "abc123"}
        back = out[0].to_dict()
        assert back["custom_emoji_id"] == "abc123"


class TestEntityDictRoundtrip:
    def test_from_dict_and_back(self) -> None:
        orig = {"type": "url", "offset": 0, "length": 10, "url": "https://example.com"}
        e = EntityDict.from_dict(orig)
        assert e.to_dict() == orig
