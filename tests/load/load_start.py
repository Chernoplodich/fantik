"""Load: 1000 /start за 60 секунд (SLA p95 < 200ms, error rate < 0.5%).

Запуск (локально, бот уже поднят с TG_API_BASE=http://localhost:9999):
    uv run locust -f tests/load/load_start.py --headless -u 1000 -r 50 -t 60s \
        --host http://localhost:8080

SLA gate — Makefile target `load-start` выставляет exit-code по CSV-отчёту.
"""

from __future__ import annotations

import hashlib
import os

from locust import FastHttpUser, constant, events, task

from tests.load.conftest import make_update_start


def _webhook_path() -> str:
    base = os.environ.get("WEBHOOK_PATH", "/webhook")
    token = os.environ.get(
        "BOT_TOKEN", "123456:TEST_TOKEN_CI_ONLY_NOT_A_REAL_BOT_TOKEN"
    )
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
    return f"{base.rstrip('/')}/{token_hash}"


_WEBHOOK = _webhook_path()
_SECRET = os.environ.get("WEBHOOK_SECRET", "")


class StartUser(FastHttpUser):
    wait_time = constant(0)

    @task
    def send_start(self) -> None:
        headers = {"Content-Type": "application/json"}
        if _SECRET:
            headers["X-Telegram-Bot-Api-Secret-Token"] = _SECRET
        self.client.post(_WEBHOOK, json=make_update_start(), headers=headers, name="/start")


@events.quitting.add_listener
def _assert_sla(environment: object, **_: object) -> None:
    """Выставляет non-zero exit, если SLA нарушено (p95 > 200 ms / err > 0.5%)."""
    stats = getattr(environment, "stats", None)
    if stats is None:
        return
    aggregated = stats.total
    p95 = aggregated.get_response_time_percentile(0.95)
    err_ratio = (aggregated.num_failures / aggregated.num_requests) if aggregated.num_requests else 0.0
    if p95 is not None and p95 > 200:
        print(f"SLA FAIL: p95={p95}ms > 200ms")
        environment.process_exit_code = 1  # type: ignore[attr-defined]
    if err_ratio > 0.005:
        print(f"SLA FAIL: error_rate={err_ratio:.4f} > 0.005")
        environment.process_exit_code = 1  # type: ignore[attr-defined]
