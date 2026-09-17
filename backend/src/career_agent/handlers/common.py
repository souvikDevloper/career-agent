"""Shared Lambda plumbing: service singletons, HTTP responses, identity, HMAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from typing import Any

from ..config import settings as cfg
from ..util import canonical_json, get_logger, uuid4
from ..workflow import Principal

logger = get_logger("http")

_services = None
_secret: str | None = None


def services():
    global _services
    if _services is None:
        from ..services import Services
        from ..store import DynamoStore

        _services = Services(DynamoStore(cfg().table_name))
    return _services


def internal_secret() -> str:
    global _secret
    if _secret is None:
        arn = os.environ.get("INTERNAL_SECRET_ARN")
        if arn:
            import boto3

            raw = boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]
            try:
                _secret = json.loads(raw)["hmac"]
            except (ValueError, KeyError):
                _secret = raw
        else:
            _secret = os.environ.get("INTERNAL_SECRET", "local-dev-secret")
    return _secret


def portal_signature(message: str) -> str:
    return hmac.new(internal_secret().encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_signature(message: str, signature: str | None) -> bool:
    return bool(signature) and hmac.compare_digest(portal_signature(message), signature or "")


SECURITY_HEADERS = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def respond(status: int, body: Any, headers: dict | None = None) -> dict:
    return {"statusCode": status, "headers": {**SECURITY_HEADERS, **(headers or {})}, "body": json.dumps(body, default=str)}


def error(status: int, code: str, message: str, correlation_id: str | None = None) -> dict:
    return respond(status, {"error": {"code": code, "message": message, "correlation_id": correlation_id}})


def body_json(event: dict) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf8", "ignore")
    if len(raw) > 256_000:
        raise ValueError("body too large")
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON object expected")
    return data


def principal(event: dict) -> Principal | None:
    """Owner is derived only from the JWT validated by API Gateway, never from client input."""
    claims = (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
    sub = claims.get("sub")
    if not sub or not re.fullmatch(r"[0-9a-fA-F-]{20,64}", str(sub)):
        return None
    groups = str(claims.get("cognito:groups", ""))
    return Principal(user_id=str(sub), is_judge="judge" in groups, email=claims.get("email"))


def correlation(event: dict) -> str:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    cid = headers.get("x-correlation-id") or ((event.get("requestContext") or {}).get("requestId")) or uuid4()
    return re.sub(r"[^A-Za-z0-9_-]", "", str(cid))[:64]


__all__ = ["services", "respond", "error", "body_json", "principal", "correlation", "portal_signature", "verify_signature",
           "canonical_json", "logger"]
