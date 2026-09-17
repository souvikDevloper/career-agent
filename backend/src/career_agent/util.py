"""Small shared helpers: ids, clocks, hashing, logging."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


def new_id(prefix: str = "") -> str:
    # time-ordered, url-safe identifier
    return f"{prefix}{int(time.time() * 1000):013d}{secrets.token_hex(5)}"


def uuid4() -> str:
    return str(uuid.uuid4())


class Clock:
    """Injectable clock so tests can control time (midnight, expiry, cooldown)."""

    def now(self) -> float:
        return time.time()

    def iso(self, ts: float | None = None) -> str:
        return datetime.fromtimestamp(self.now() if ts is None else ts, tz=timezone.utc).isoformat(timespec="seconds")


class FixedClock(Clock):
    def __init__(self, ts: float) -> None:
        self.ts = ts

    def now(self) -> float:
        return self.ts

    def advance(self, seconds: float) -> None:
        self.ts += seconds


def local_date(ts: float, tz_name: str) -> str:
    tz = timezone.utc
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(tz_name)  # type: ignore[assignment]
        except Exception:
            tz = timezone.utc
    return datetime.fromtimestamp(ts, tz=tz).strftime("%Y-%m-%d")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(data: Any) -> str:
    raw = data if isinstance(data, (bytes, bytearray)) else canonical_json(data).encode()
    return hashlib.sha256(raw).hexdigest()


_SENSITIVE = {"resume_text", "token", "password", "authorization", "email_body", "cookie", "answers", "facts"}


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("[redacted]" if k.lower() in _SENSITIVE else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj[:20]]
    if isinstance(obj, str) and len(obj) > 300:
        return obj[:300] + "…"
    return obj


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    logger.propagate = False
    return logger


def log(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Structured, redacted JSON log line with correlation id support."""
    logger.info(canonical_json({"event": event, **redact(fields)}))
