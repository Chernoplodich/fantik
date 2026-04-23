"""Unit-тесты interpret_segment: валидация всех kind + ошибки."""

from __future__ import annotations

import pytest

from app.domain.broadcasts.exceptions import SegmentValidationError
from app.domain.broadcasts.segment import describe_segment, interpret_segment


def test_all_kind_ok() -> None:
    plan = interpret_segment({"kind": "all"})
    assert plan.kind == "all"
    assert plan.days is None
    assert plan.author_id is None


def test_active_since_days_ok() -> None:
    plan = interpret_segment({"kind": "active_since_days", "value": 7})
    assert plan.kind == "active_since_days"
    assert plan.days == 7


@pytest.mark.parametrize("bad", [0, -1, 4000, "x", None])
def test_active_since_days_invalid(bad: object) -> None:
    with pytest.raises(SegmentValidationError):
        interpret_segment({"kind": "active_since_days", "value": bad})


def test_authors_kind_ok() -> None:
    plan = interpret_segment({"kind": "authors"})
    assert plan.kind == "authors"


def test_subscribers_of_ok() -> None:
    plan = interpret_segment({"kind": "subscribers_of", "author_id": 42})
    assert plan.kind == "subscribers_of"
    assert plan.author_id == 42


@pytest.mark.parametrize("bad", [0, -1, None, "x"])
def test_subscribers_of_invalid(bad: object) -> None:
    with pytest.raises(SegmentValidationError):
        interpret_segment({"kind": "subscribers_of", "author_id": bad})


def test_utm_ok() -> None:
    plan = interpret_segment({"kind": "utm", "code": "XYZ123"})
    assert plan.utm_code == "XYZ123"


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_utm_invalid(bad: object) -> None:
    with pytest.raises(SegmentValidationError):
        interpret_segment({"kind": "utm", "code": bad})


def test_retry_failed_ok() -> None:
    plan = interpret_segment({"kind": "retry_failed", "parent_broadcast_id": 7})
    assert plan.parent_broadcast_id == 7


def test_unknown_kind_raises() -> None:
    with pytest.raises(SegmentValidationError):
        interpret_segment({"kind": "wtf_this_does_not_exist"})


def test_empty_spec_raises() -> None:
    with pytest.raises(SegmentValidationError):
        interpret_segment({})
    with pytest.raises(SegmentValidationError):
        interpret_segment(None)


def test_describe_segment_covers_all() -> None:
    cases = [
        ({"kind": "all"}, "Все пользователи"),
        ({"kind": "active_since_days", "value": 7}, "Активные за последние 7"),
        ({"kind": "authors"}, "Авторы"),
        ({"kind": "subscribers_of", "author_id": 42}, "Подписчики автора #42"),
        ({"kind": "utm", "code": "abc"}, "UTM"),
        (
            {"kind": "retry_failed", "parent_broadcast_id": 11},
            "упавшие в рассылке #11",
        ),
    ]
    for spec, expected_substr in cases:
        assert expected_substr in describe_segment(spec)
