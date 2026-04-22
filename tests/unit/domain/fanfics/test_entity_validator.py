"""Unit-тесты entity_validator."""

from __future__ import annotations

import pytest

from app.domain.fanfics.exceptions import InvalidEntityError
from app.domain.fanfics.services.entity_validator import validate


class TestEntityValidator:
    def test_empty_returns_empty(self) -> None:
        assert validate("hello", None) == []
        assert validate("hello", []) == []

    def test_spoiler_bold_italic_ok(self) -> None:
        text = "hello world"
        entities = [
            {"type": "bold", "offset": 0, "length": 5},
            {"type": "italic", "offset": 6, "length": 5},
            {"type": "spoiler", "offset": 0, "length": 11},
        ]
        result = validate(text, entities)
        assert len(result) == 3
        # отсортировано по (offset, -length)
        assert result[0]["offset"] == 0

    def test_javascript_url_rejected(self) -> None:
        text = "click"
        entities = [
            {
                "type": "text_link",
                "offset": 0,
                "length": 5,
                "url": "javascript:alert(1)",
            }
        ]
        with pytest.raises(InvalidEntityError):
            validate(text, entities)

    def test_data_url_rejected(self) -> None:
        text = "xxx"
        entities = [
            {
                "type": "text_link",
                "offset": 0,
                "length": 3,
                "url": "data:text/html,<script>",
            }
        ]
        with pytest.raises(InvalidEntityError):
            validate(text, entities)

    def test_text_mention_rejected(self) -> None:
        with pytest.raises(InvalidEntityError):
            validate(
                "user",
                [
                    {
                        "type": "text_mention",
                        "offset": 0,
                        "length": 4,
                        "user": {"id": 1},
                    }
                ],
            )

    def test_custom_emoji_requires_id(self) -> None:
        with pytest.raises(InvalidEntityError):
            validate("x", [{"type": "custom_emoji", "offset": 0, "length": 1}])

    def test_custom_emoji_with_id_ok(self) -> None:
        result = validate(
            "x",
            [
                {
                    "type": "custom_emoji",
                    "offset": 0,
                    "length": 1,
                    "custom_emoji_id": "abc",
                }
            ],
        )
        assert result[0]["custom_emoji_id"] == "abc"

    def test_out_of_bounds_rejected(self) -> None:
        with pytest.raises(InvalidEntityError):
            validate("abc", [{"type": "bold", "offset": 2, "length": 10}])

    def test_https_text_link_ok(self) -> None:
        result = validate(
            "go",
            [
                {
                    "type": "text_link",
                    "offset": 0,
                    "length": 2,
                    "url": "https://example.com",
                }
            ],
        )
        assert result[0]["url"] == "https://example.com"

    def test_too_many_entities_rejected(self) -> None:
        text = "a" * 2000
        entities = [{"type": "bold", "offset": i, "length": 1} for i in range(1001)]
        with pytest.raises(InvalidEntityError):
            validate(text, entities)

    def test_utf16_surrogate_length(self) -> None:
        # 😀 = 2 UTF-16 units
        text = "😀 hi"  # utf16_length = 2 + 3 = 5
        result = validate(text, [{"type": "bold", "offset": 0, "length": 5}])
        assert result[0]["length"] == 5
