"""Ashby public job board discovery.

Ashby serves each customer's listed roles from a documented, key-free job board
endpoint. Read-only and public, like the Greenhouse and Lever boards. Submitting
needs the employer's credentials, so applying stays a prepared manual handoff.
"""

from __future__ import annotations

import re
from typing import Any

from ..util import sha256
from .http import fetch_json

HOSTS = {"api.ashbyhq.com"}
SOURCE = "ashby-public"
BOARD_RE = r"[A-Za-z0-9][A-Za-z0-9._-]{1,60}"


def normalize(company: str, raw: dict) -> dict:
    location = raw.get("location") or ""
    secondary = [s.get("location") for s in (raw.get("secondaryLocations") or []) if isinstance(s, dict)]
    if secondary:
        location = ", ".join([location, *[s for s in secondary if s]]) if location else ", ".join(s for s in secondary if s)
    job = {
        "job_key": f"ashby:{company}:{raw['id']}",
        "canonical_key": f"ashby:{company}:{raw['id']}",
        "source": SOURCE,
        "board": company,
        "external_id": str(raw["id"]),
        "company": company.replace("-", " ").title(),
        "title": (raw.get("title") or "").strip(),
        "location": location,
        "work_mode": "remote" if raw.get("isRemote") or "remote" in location.lower() else None,
        "employment_type": (raw.get("employmentType") or "").lower() or None,
        "description": (raw.get("descriptionPlain") or "").strip()[:12000],
        "url": raw.get("jobUrl"),
        "apply": {"kind": "external", "url": raw.get("applyUrl") or raw.get("jobUrl")},
        "published_at": raw.get("publishedAt"),
        "updated_at": raw.get("updatedAt") or raw.get("publishedAt"),
        "departments": [d for d in (raw.get("department"), raw.get("team")) if d],
        "requirements": None,  # extracted lazily by the model, only for candidate matches
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def fetch_board(company: str) -> list[dict]:
    if not re.fullmatch(BOARD_RE, company):
        raise ValueError("invalid ashby company token")
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
    data: Any = fetch_json(url, HOSTS, timeout=20)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []
    # isListed false means the employer has unpublished it; do not surface those.
    return [normalize(company, j) for j in jobs
            if isinstance(j, dict) and j.get("id") and j.get("isListed", True)]
