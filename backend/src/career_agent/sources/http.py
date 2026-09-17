"""Minimal, safe outbound HTTP (stdlib) with allowlisted hosts, size and time limits."""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_BYTES = 4 * 1024 * 1024


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _allowed(url: str, allow_hosts: set[str]) -> None:
    parts = urllib.parse.urlparse(url)
    if parts.scheme != "https":
        raise FetchError("only https URLs are allowed")
    host = parts.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in allow_hosts):
        raise FetchError(f"host not allowed: {host}")
    try:
        for info in socket.getaddrinfo(host, 443):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise FetchError("private network destinations are blocked")
    except socket.gaierror as exc:
        raise FetchError(f"dns failure for {host}") from exc


def fetch(url: str, allow_hosts: set[str], *, method: str = "GET", body: bytes | None = None,
          headers: dict | None = None, timeout: float = 15.0) -> tuple[int, bytes, dict]:
    _allowed(url, allow_hosts)
    req = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "CareerAgent/1.0 (+hackathon)", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (scheme checked)
            data = res.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise FetchError("response too large")
            return res.status, data, dict(res.headers)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}", exc.code, exc.headers.get("Retry-After") if exc.headers else None) from exc
    except urllib.error.URLError as exc:
        raise FetchError(f"network error: {exc.reason}") from exc


def fetch_json(url: str, allow_hosts: set[str], **kw: Any) -> Any:
    _, data, _ = fetch(url, allow_hosts, **kw)
    return json.loads(data.decode("utf8"))
