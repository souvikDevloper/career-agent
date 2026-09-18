"""Greenhouse public job board discovery (no key required for GET endpoints)."""

from __future__ import annotations

import html
import re
from typing import Any

from ..util import sha256
from .http import fetch_json

HOSTS = {"boards-api.greenhouse.io"}
SOURCE = "greenhouse-public"


def html_to_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _requisition(raw: dict) -> str:
    """Greenhouse's requisition_id is free text and boards abuse it.

    Stripe returns the literal sentence "See Opening ID" for all 665 of its
    postings, which collapsed the whole board to a single canonical key. Only
    accept something that looks like an identifier; otherwise fall back to the
    posting id, which is always unique.
    """
    value = str(raw.get("requisition_id") or "").strip()
    return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{1,48}", value) else str(raw["id"])


def normalize(board: str, raw: dict) -> dict:
    description = html_to_text(raw.get("content", ""))
    loc = (raw.get("location") or {}).get("name") or ""
    job = {
        "job_key": f"greenhouse:{board}:{raw['id']}",
        "canonical_key": f"greenhouse:{board}:{_requisition(raw)}",
        "source": SOURCE,
        "board": board,
        "external_id": str(raw["id"]),
        "company": board.replace("-", " ").title(),
        "title": raw.get("title", "").strip(),
        "location": loc,
        "work_mode": "remote" if "remote" in loc.lower() else None,
        "description": description[:12000],
        "url": raw.get("absolute_url"),
        "apply": {"kind": "external", "url": raw.get("absolute_url")},
        "published_at": raw.get("first_published") or raw.get("updated_at"),
        "updated_at": raw.get("updated_at"),
        "departments": [d.get("name") for d in raw.get("departments") or []],
        "requirements": None,  # extracted lazily by the model only for candidate matches
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def fetch_board(board: str) -> list[dict]:
    if not re.fullmatch(r"[a-z0-9-]{2,60}", board):
        raise ValueError("invalid board token")
    data: Any = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true", HOSTS, timeout=20)
    return [normalize(board, j) for j in data.get("jobs", [])]
