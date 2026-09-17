"""Serve the built single-page app from S3 through the HTTP API.

CloudFront is the intended front door. New AWS accounts cannot create a
distribution until account activation finishes - ``CreateDistribution`` returns
403 regardless of IAM - so this handler lets the same HTTP API that already
serves ``/api/*`` and ``/portal`` also serve the UI, on the same origin.

It reproduces what the distribution does for the web origin: extensionless paths
rewrite to ``index.html`` (client-side routing), the bucket stays private and is
read with IAM, and the security headers - including the Permissions-Policy that
allows the microphone - are set here instead of by a ResponseHeadersPolicy.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from ..util import get_logger

logger = get_logger("web")

_s3 = None

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
}

TEXTUAL = {".html", ".js", ".mjs", ".css", ".json", ".svg", ".map", ".txt"}

SECURITY = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
}


def s3():
    global _s3
    if _s3 is None:
        import boto3

        _s3 = boto3.client("s3")
    return _s3


def _ext(key: str) -> str:
    dot = key.rfind(".")
    slash = key.rfind("/")
    return key[dot:].lower() if dot > slash else ""


def _key_for(path: str) -> str:
    """Map a request path to an object key, mirroring the SPA rewrite."""
    key = (path or "/").lstrip("/")
    if not key:
        return "index.html"
    # A path with no file extension is a client-side route, not an asset.
    if "." not in key.rsplit("/", 1)[-1]:
        return "index.html"
    return key


def _response(status: int, body: str, content_type: str, cache: str, b64: bool = False) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type, "Cache-Control": cache, **SECURITY},
        "body": body,
        "isBase64Encoded": b64,
    }


def handler(event: dict, context: Any) -> dict:
    bucket = os.environ["WEB_BUCKET"]
    path = (event.get("rawPath") or "/").split("?", 1)[0]
    key = _key_for(path)

    try:
        obj = s3().get_object(Bucket=bucket, Key=key)
    except Exception:
        # A missing asset is a genuine 404; a missing route falls back to the app
        # shell so deep links keep working exactly as they do behind CloudFront.
        if key == "index.html":
            return _response(503, "The app has not been published yet.", "text/plain; charset=utf-8", "no-store")
        try:
            obj = s3().get_object(Bucket=bucket, Key="index.html")
            key = "index.html"
        except Exception:
            return _response(404, "Not found", "text/plain; charset=utf-8", "no-store")

    raw = obj["Body"].read()
    ext = _ext(key)
    ctype = TYPES.get(ext, obj.get("ContentType") or "application/octet-stream")

    # Content-hashed assets are immutable; the shell and runtime config are not.
    if key.startswith("assets/") and key != "index.html":
        cache = "public, max-age=31536000, immutable"
    else:
        cache = "no-cache"

    if ext in TEXTUAL:
        return _response(200, raw.decode("utf-8"), ctype, cache)
    return _response(200, base64.b64encode(raw).decode("ascii"), ctype, cache, b64=True)
