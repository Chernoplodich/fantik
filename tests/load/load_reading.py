"""Load: 500 юзеров × 10 минут листают случайные approved-фики.

SLA: p95 read_page < 150 мс, error rate < 0.5%.

Требует, чтобы в БД был seed-набор: ≥100 approved фиков × 10 глав. Минимальный
seed-скрипт предполагается отдельным pytest-fixture / data-seeding шагом, в
рамках Этапа 7 не реализован (достаточно синтетики на 1 фик для smoke'а).
"""

from __future__ import annotations

import hashlib
import os
import random

from locust import FastHttpUser, between, events, task

from tests.load.conftest import make_callback


def _webhook_path() -> str:
    base = os.environ.get("WEBHOOK_PATH", "/webhook")
    token = os.environ.get(
        "BOT_TOKEN", "123456:TEST_TOKEN_CI_ONLY_NOT_A_REAL_BOT_TOKEN"
    )
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
    return f"{base.rstrip('/')}/{token_hash}"


_WEBHOOK = _webhook_path()
_SECRET = os.environ.get("WEBHOOK_SECRET", "")
_HEADERS = {"Content-Type": "application/json"}
if _SECRET:
    _HEADERS["X-Telegram-Bot-Api-Secret-Token"] = _SECRET

# ID фика и количества глав/страниц берём из env — seed'ить LOAD-данные через
# Makefile/conftest, а сценарий читает готовый пул.
_FIC_IDS = [int(x) for x in os.environ.get("LOAD_FIC_IDS", "1").split(",")]
_MAX_CHAPTER = int(os.environ.get("LOAD_MAX_CHAPTER", "10"))
_MAX_PAGE = int(os.environ.get("LOAD_MAX_PAGE", "30"))


class Reader(FastHttpUser):
    wait_time = between(1, 3)
    tg_id = 0  # заполняется per-instance в on_start

    def on_start(self) -> None:
        self.tg_id = random.randint(1_000_000_000, 9_999_999_999)

    @task(1)
    def open_fic(self) -> None:
        fic_id = random.choice(_FIC_IDS)
        self.client.post(
            _WEBHOOK,
            json=make_callback(f"reader:open:{fic_id}", tg_id=self.tg_id),
            headers=_HEADERS,
            name="reader:open",
        )

    @task(5)
    def read_page(self) -> None:
        fic_id = random.choice(_FIC_IDS)
        ch = random.randint(1, _MAX_CHAPTER)
        pg = random.randint(1, _MAX_PAGE)
        self.client.post(
            _WEBHOOK,
            json=make_callback(f"reader:page:{fic_id}:{ch}:{pg}", tg_id=self.tg_id),
            headers=_HEADERS,
            name="reader:page",
        )


@events.quitting.add_listener
def _assert_sla(environment: object, **_: object) -> None:
    stats = getattr(environment, "stats", None)
    if stats is None:
        return
    # p95 по операции `reader:page` — это «page read» SLA.
    page_entry = next(
        (s for n, s in stats.entries.items() if n[0] == "reader:page"),  # type: ignore[attr-defined]
        None,
    )
    if page_entry is not None:
        p95 = page_entry.get_response_time_percentile(0.95)
        if p95 is not None and p95 > 150:
            print(f"SLA FAIL: reader:page p95={p95}ms > 150ms")
            environment.process_exit_code = 1  # type: ignore[attr-defined]
    total = stats.total
    err_ratio = (total.num_failures / total.num_requests) if total.num_requests else 0.0
    if err_ratio > 0.005:
        print(f"SLA FAIL: error_rate={err_ratio:.4f} > 0.005")
        environment.process_exit_code = 1  # type: ignore[attr-defined]
