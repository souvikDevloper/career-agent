"""Runtime configuration resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    table_name: str = field(default_factory=lambda: _env("TABLE_NAME", "career-agent"))
    bucket: str = field(default_factory=lambda: _env("BUCKET_NAME"))
    region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))
    model_id: str = field(default_factory=lambda: _env("MODEL_ID", "us.amazon.nova-2-lite-v1:0"))
    # Bedrock is the default and the model this project is built on. "openai"
    # selects an OpenAI-compatible endpoint, used only while Bedrock is blocked
    # on this account; which one answered is always reported, never hidden.
    model_provider: str = field(default_factory=lambda: _env("MODEL_PROVIDER", "bedrock").lower())
    model_api_base: str = field(default_factory=lambda: _env("MODEL_API_BASE"))
    model_api_key_param: str = field(default_factory=lambda: _env("MODEL_API_KEY_PARAM"))
    fallback_model_id: str = field(default_factory=lambda: _env("FALLBACK_MODEL_ID"))
    work_queue_url: str = field(default_factory=lambda: _env("WORK_QUEUE_URL"))
    submit_queue_url: str = field(default_factory=lambda: _env("SUBMIT_QUEUE_URL"))
    notify_queue_url: str = field(default_factory=lambda: _env("NOTIFY_QUEUE_URL"))
    user_pool_id: str = field(default_factory=lambda: _env("USER_POOL_ID"))
    user_pool_client_id: str = field(default_factory=lambda: _env("USER_POOL_CLIENT_ID"))
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL"))
    api_base_url: str = field(default_factory=lambda: _env("API_BASE_URL"))
    ses_sender: str = field(default_factory=lambda: _env("SES_SENDER"))
    telegram_secret_arn: str = field(default_factory=lambda: _env("TELEGRAM_SECRET_PARAM"))
    transcribe_role_arn: str = field(default_factory=lambda: _env("TRANSCRIBE_ROLE_ARN"))
    greenhouse_boards: tuple[str, ...] = field(
        default_factory=lambda: tuple(b.strip() for b in _env("GREENHOUSE_BOARDS", "").split(",") if b.strip())
    )
    lever_boards: tuple[str, ...] = field(
        default_factory=lambda: tuple(b.strip() for b in _env("LEVER_BOARDS", "").split(",") if b.strip())
    )
    ashby_boards: tuple[str, ...] = field(
        default_factory=lambda: tuple(b.strip() for b in _env("ASHBY_BOARDS", "").split(",") if b.strip())
    )
    # Workday tenants, each "tenant:pod:site" - e.g. paypal:wd1:jobs
    workday_boards: tuple[str, ...] = field(
        default_factory=lambda: tuple(b.strip() for b in _env("WORKDAY_BOARDS", "").split(",") if b.strip())
    )
    # Oracle HCM sites, each "tenant:site" or "tenant:site:COUNTRY" - e.g. jpmc:CX_1001:IN
    oracle_boards: tuple[str, ...] = field(
        default_factory=lambda: tuple(b.strip() for b in _env("ORACLE_BOARDS", "").split(",") if b.strip())
    )
    # Adzuna aggregator boards, each "COUNTRY" or "COUNTRY:query" - e.g. in or in:python.
    # Inert without a key: the connector is registered either way so the UI can say
    # it exists and is unconfigured, rather than pretending it is not there.
    adzuna_boards: tuple[str, ...] = field(
        default_factory=lambda: tuple(b.strip() for b in _env("ADZUNA_BOARDS", "").split(",") if b.strip())
    )
    adzuna_app_id: str = field(default_factory=lambda: _env("ADZUNA_APP_ID"))
    adzuna_app_key: str = field(default_factory=lambda: _env("ADZUNA_APP_KEY"))
    # Amazon Jobs, each "COUNTRY" or "COUNTRY:query" - e.g. IND or IND:intern
    amazon_boards: tuple[str, ...] = field(
        default_factory=lambda: tuple(b.strip() for b in _env("AMAZON_BOARDS", "").split(",") if b.strip())
    )
    # The fictional employer exists only for the end-to-end submission demo, which
    # is the one place a real browser submission can honestly be shown. Off by
    # default: it has no business in a product that answers questions about real
    # jobs, and a fictional company competing with real openings is what made
    # results look invented.
    enable_test_employer: bool = field(default_factory=lambda: _env("ENABLE_TEST_EMPLOYER", "").lower() == "true")
    global_daily_model_calls: int = field(default_factory=lambda: int(_env("GLOBAL_DAILY_MODEL_CALLS", "4000")))
    user_daily_model_calls: int = field(default_factory=lambda: int(_env("USER_DAILY_MODEL_CALLS", "300")))
    judge_daily_model_calls: int = field(default_factory=lambda: int(_env("JUDGE_DAILY_MODEL_CALLS", "80")))
    judge_voice_seconds: int = field(default_factory=lambda: int(_env("JUDGE_VOICE_SECONDS", "240")))
    user_voice_seconds: int = field(default_factory=lambda: int(_env("USER_VOICE_SECONDS", "900")))
    demo_sessions_per_hour: int = field(default_factory=lambda: int(_env("DEMO_SESSIONS_PER_HOUR", "60")))
    stage: str = field(default_factory=lambda: _env("STAGE", "prod"))


def settings() -> Settings:
    return Settings()
