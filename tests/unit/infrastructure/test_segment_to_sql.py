"""Snapshot-тесты SQL-билдера сегментов для рассылок.

Проверяем, что build_segment_where компилируется в ожидаемую подстроку SQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from app.domain.broadcasts.segment import interpret_segment
from app.infrastructure.db.repositories.user_segment import build_segment_where


def _compile(spec: dict) -> str:
    plan = interpret_segment(spec)
    clause = build_segment_where(plan)
    return str(
        clause.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


def test_all_kind_compiles() -> None:
    sql = _compile({"kind": "all"})
    assert "users.id is not null" in sql


def test_active_since_days_uses_make_interval() -> None:
    sql = _compile({"kind": "active_since_days", "value": 7})
    assert "make_interval" in sql
    assert "last_seen_at" in sql


def test_authors_has_exists_approved_fanfic() -> None:
    sql = _compile({"kind": "authors"})
    assert "exists" in sql
    assert "fanfics" in sql
    assert "approved" in sql
    assert "author_nick" in sql


def test_subscribers_of_uses_subscriptions_table() -> None:
    sql = _compile({"kind": "subscribers_of", "author_id": 42})
    assert "subscriptions" in sql
    assert "42" in sql


def test_utm_references_tracking_codes() -> None:
    sql = _compile({"kind": "utm", "code": "xyz"})
    assert "tracking_codes" in sql
    assert "xyz" in sql


@pytest.mark.parametrize(
    "spec",
    [
        {"kind": "all"},
        {"kind": "active_since_days", "value": 30},
        {"kind": "authors"},
        {"kind": "subscribers_of", "author_id": 1},
        {"kind": "utm", "code": "abc"},
    ],
)
def test_all_presets_compile_without_error(spec: dict) -> None:
    # Просто проверяем, что не падает.
    _compile(spec)
