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


def normalize(board: str, raw: dict) -> dict:
    description = html_to_text(raw.get("content", ""))
    loc = (raw.get("location") or {}).get("name") or ""
    job = {
        "job_key": f"greenhouse:{board}:{raw['id']}",
        "canonical_key": f"greenhouse:{board}:{raw.get('requisition_id') or raw['id']}",
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
