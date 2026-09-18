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
    global_daily_model_calls: int = field(default_factory=lambda: int(_env("GLOBAL_DAILY_MODEL_CALLS", "4000")))
    user_daily_model_calls: int = field(default_factory=lambda: int(_env("USER_DAILY_MODEL_CALLS", "300")))
    judge_daily_model_calls: int = field(default_factory=lambda: int(_env("JUDGE_DAILY_MODEL_CALLS", "80")))
    judge_voice_seconds: int = field(default_factory=lambda: int(_env("JUDGE_VOICE_SECONDS", "240")))
    user_voice_seconds: int = field(default_factory=lambda: int(_env("USER_VOICE_SECONDS", "900")))
    demo_sessions_per_hour: int = field(default_factory=lambda: int(_env("DEMO_SESSIONS_PER_HOUR", "60")))
    stage: str = field(default_factory=lambda: _env("STAGE", "prod"))


def settings() -> Settings:
    return Settings()
