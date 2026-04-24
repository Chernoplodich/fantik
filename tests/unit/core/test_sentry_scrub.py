"""Проверка Sentry before_send: PII никогда не уезжает в Sentry."""

from __future__ import annotations

from app.core.sentry import scrub_pii_event


def test_scrub_user_to_id_only() -> None:
    ev = {"user": {"id": 42, "username": "x", "first_name": "Ivan"}}
    scrubbed = scrub_pii_event(ev, None)
    assert scrubbed == {"user": {"id": 42}}


def test_scrub_user_missing_id() -> None:
    ev = {"user": {"username": "x"}}
    scrubbed = scrub_pii_event(ev, None)
    assert scrubbed == {"user": {}}


def test_scrub_pii_from_extras() -> None:
    ev = {
        "extra": {"text": "секрет", "fic_id": 10, "first_name": "Ivan"},
        "tags": {"handler": "start", "token": "abc123"},
    }
    out = scrub_pii_event(ev, None) or {}
    assert out["extra"] == {"fic_id": 10}
    assert out["tags"] == {"handler": "start"}


def test_scrub_breadcrumb_messages_for_telegram() -> None:
    ev = {
        "breadcrumbs": {
            "values": [
                {"category": "telegram.update", "message": "text=секрет", "data": {"caption": "foo"}},
                {"category": "db.query", "message": "SELECT 1", "data": {"sql": "SELECT 1"}},
            ]
        }
    }
    out = scrub_pii_event(ev, None) or {}
    values = out["breadcrumbs"]["values"]
    assert values[0]["message"] == "<scrubbed>"
    assert "caption" not in values[0]["data"]
    # Не-telegram breadcrumb сохраняется (нет PII-ключей в data).
    assert values[1]["data"] == {"sql": "SELECT 1"}


def test_scrub_nested_dicts() -> None:
    ev = {
        "contexts": {
            "tg_update": {"message": {"text": "hello", "first_name": "Ivan"}},
        }
    }
    out = scrub_pii_event(ev, None) or {}
    msg = out["contexts"]["tg_update"]["message"]
    assert "text" not in msg
    assert "first_name" not in msg
