"""Lever public postings discovery.

Lever publishes each customer's open roles at a documented, key-free endpoint,
which is the same footing as the Greenhouse boards: read-only, public, and
intended to be consumed. Submitting still needs the employer's credentials, so
applying through Lever stays a prepared manual handoff rather than an automated
submission - the same line this project draws for every live employer.
"""

from __future__ import annotations

from typing import Any

from ..util import sha256
from .http import fetch_json

HOSTS = {"api.lever.co"}
SOURCE = "lever-public"
BOARD_RE = r"[A-Za-z0-9][A-Za-z0-9._-]{1,60}"


def normalize(company: str, raw: dict) -> dict:
    cats = raw.get("categories") or {}
    location = cats.get("location") or ""
    commitment = (cats.get("commitment") or "").lower()
    workplace = (raw.get("workplaceType") or "").lower()
    description = (raw.get("descriptionPlain") or "").strip()
    lists = raw.get("lists") or []
    for block in lists:
        text = (block.get("text") or "").strip()
        content = (block.get("content") or "")
        if text:
            description += f"\n\n{text}\n{content}"
    job = {
        "job_key": f"lever:{company}:{raw['id']}",
        "canonical_key": f"lever:{company}:{raw['id']}",
        "source": SOURCE,
        "board": company,
        "external_id": str(raw["id"]),
        "company": company.replace("-", " ").title(),
        "title": (raw.get("text") or "").strip(),
        "location": location,
        # Lever publishes all three modes and the employer set it deliberately, so
        # pass it through rather than guessing. Scoring falls back to reading the
        # location text when a board does not say.
        "work_mode": workplace if workplace in {"remote", "hybrid", "onsite"} else None,
        "employment_type": commitment or None,
        "description": description[:12000],
        "url": raw.get("hostedUrl"),
        # Submission needs the employer's key, so this is a handoff, not an apply.
        "apply": {"kind": "external", "url": raw.get("applyUrl") or raw.get("hostedUrl")},
        "published_at": raw.get("createdAt"),
        "updated_at": raw.get("updatedAt") or raw.get("createdAt"),
        "departments": [d for d in (cats.get("team"), cats.get("department")) if d],
        "requirements": None,  # extracted lazily by the model, only for candidate matches
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def fetch_board(company: str) -> list[dict]:
    import re

    if not re.fullmatch(BOARD_RE, company):
        raise ValueError("invalid lever company token")
    data: Any = fetch_json(f"https://api.lever.co/v0/postings/{company}?mode=json", HOSTS, timeout=20)
    if not isinstance(data, list):
        return []
    return [normalize(company, j) for j in data if isinstance(j, dict) and j.get("id")]
