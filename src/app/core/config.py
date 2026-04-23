"""Конфигурация приложения: pydantic-settings из .env / переменных окружения."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppEnv(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"
    TEST = "test"


class RunMode(StrEnum):
    POLLING = "polling"
    WEBHOOK = "webhook"


class SearchBackend(StrEnum):
    MEILI = "meili"
    PG = "pg"


class LogRenderer(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    """Единая точка доступа к конфигурации. Читается из env/.env при старте процесса."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- app ----------
    app_env: AppEnv = AppEnv.DEV
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_renderer: LogRenderer = LogRenderer.CONSOLE
    release: str = ""

    # ---------- telegram ----------
    bot_token: SecretStr
    # NoDecode: не даём pydantic-settings парсить как JSON — обрабатываем в
    # валидаторе ниже (поддержка "1,2,3"-формата env-строки).
    admin_tg_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    bot_run_mode: RunMode = RunMode.POLLING

    webhook_base_url: str = ""
    webhook_path: str = "/webhook"
    webhook_secret: SecretStr = SecretStr("")
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    health_host: str = "0.0.0.0"
    health_port: int = 8080
    metrics_port: int = 8081

    @field_validator("admin_tg_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> list[int]:
        if v is None or v == "":
            return []
        if isinstance(v, int):  # одиночный ID в env, pydantic JSON-распарсил как int
            return [v]
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        raise TypeError(f"admin_tg_ids: unexpected type {type(v)!r}")

    # ---------- postgres ----------
    postgres_user: str = "fantik"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "fantik"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_dsn: str = ""  # если заполнен — перекрывает сборку
    postgres_pool_size: int = 10
    postgres_max_overflow: int = 10
    postgres_pool_timeout: int = 30
    postgres_pool_recycle: int = 1800
    postgres_echo: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def postgres_url(self) -> str:
        if self.postgres_dsn:
            return self.postgres_dsn
        pw = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pw}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---------- redis ----------
    redis_url: str = "redis://redis:6379/0"
    redis_fsm_db: int = 1
    redis_taskiq_db: int = 2
    redis_cache_db: int = 0

    def redis_url_for(self, db: int) -> str:
        """Построить URL с конкретной БД (Redis принимает /N как номер БД в URL)."""
        if "?" in self.redis_url:
            base, query = self.redis_url.split("?", 1)
            base = base.rstrip("/0123456789")
            if not base.endswith("/"):
                base += "/"
            return f"{base}{db}?{query}"
        base = self.redis_url.rstrip("/")
        if base[-2:-1] == "/" and base[-1].isdigit():
            base = base[:-2]
        elif base[-1].isdigit() and "/" in base:
            head, tail = base.rsplit("/", 1)
            if tail.isdigit():
                base = head
        return f"{base}/{db}"

    # ---------- meilisearch ----------
    meili_url: str = "http://meilisearch:7700"
    meili_master_key: SecretStr
    search_backend: SearchBackend = SearchBackend.MEILI

    # ---------- taskiq ----------
    taskiq_queue_default: str = "fantik:tasks"
    taskiq_queue_broadcast: str = "fantik:broadcast"

    # ---------- broadcast ----------
    broadcast_rate: float = 25.0
    broadcast_rate_capacity: int = 25
    broadcast_rate_paid: float = 1000.0
    broadcast_rate_paid_capacity: int = 1000
    broadcast_delivery_max_attempts: int = 3
    broadcast_max_active: int = 3
    allow_paid_broadcast: bool = False

    # ---------- time ----------
    default_timezone: str = "Europe/Moscow"

    # ---------- sentry ----------
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.01

    # ---------- domain limits ----------
    max_chapters_per_fic: int = 200
    max_chapter_chars: int = 100_000
    max_fics_per_day: int = 3
    max_reports_per_day: int = 20
    max_user_updates_per_min: int = 30
    page_limit_utf16: int = 3_900

    # ---------- derived ----------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_prod(self) -> bool:
        return self.app_env == AppEnv.PROD

    @computed_field  # type: ignore[prop-decorator]
    @property
    def webhook_full_url(self) -> str:
        """Полный URL для setWebhook: base + path + sha256(token)."""
        import hashlib

        if not self.webhook_base_url:
            return ""
        token_hash = hashlib.sha256(self.bot_token.get_secret_value().encode()).hexdigest()[:32]
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path.rstrip('/')}/{token_hash}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированный singleton. Использовать из main-процессов и DI-провайдеров."""
    return Settings()
