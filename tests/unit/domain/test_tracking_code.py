"""Тесты генератора и валидации UTM-кода."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.domain.tracking.value_objects import TrackingCodeStr, generate_code


class TestTrackingCodeStr:
    @pytest.mark.parametrize("good", ["abc12345", "A1b2C3d4", "XYZ89012"])
    def test_accepts_valid(self, good: str) -> None:
        assert str(TrackingCodeStr(good)) == good

    @pytest.mark.parametrize("bad", ["", "abc12", "abc-12345", "abc 12345", "z" * 17, "abcäb1"])
    def test_rejects_invalid(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            TrackingCodeStr(bad)


class TestGenerateCode:
    def test_default_length_is_8(self) -> None:
        code = generate_code()
        assert len(code) == 8

    def test_custom_length(self) -> None:
        code = generate_code(12)
        assert len(code) == 12

    def test_only_base62_chars(self) -> None:
        for _ in range(50):
            code = generate_code()
            assert all(c.isalnum() for c in code)

    def test_length_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            generate_code(3)
        with pytest.raises(ValidationError):
            generate_code(20)

    def test_codes_are_unique_enough(self) -> None:
        # statistical — не математическая гарантия, но 8 base62 символов = 62^8 ≈ 2e14
        codes = {str(generate_code()) for _ in range(200)}
        assert len(codes) == 200
