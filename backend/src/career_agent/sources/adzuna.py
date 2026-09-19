"""Adzuna: an aggregator, for breadth beyond the boards we connect to directly.

Every other connector here reads one employer's own ATS, which is accurate but
only ever covers employers we have wired up. Adzuna indexes the wider market,
including Indian employers with no public ATS feed at all, and its free tier
needs nothing but a registered key.

Deliberately second-class. An aggregator's copy of a posting is a copy: the
description is often truncated and applying goes through a redirect rather than
the employer's own form, so these can be discovered and scored but never
submitted to. Configured as "COUNTRY" or "COUNTRY:query", e.g. "in" or "in:python".
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from ..util import sha256
from .http import fetch_json

HOSTS = {"api.adzuna.com"}
SOURCE = "adzuna-public"
BASE = "https://api.adzuna.com/v1/api/jobs"
SPEC_RE = re.compile(r"^([a-z]{2})(?::([A-Za-z0-9 +#._-]{1,60}))?$")


def parse_spec(spec: str) -> tuple[str, str]:
    hit = SPEC_RE.match((spec or "").strip())
    if not hit:
        raise ValueError("adzuna board must look like COUNTRY or COUNTRY:query, e.g. in or in:python")
    return hit.group(1), (hit.group(2) or "").strip()


def normalize(country: str, raw: dict) -> dict:
    external_id = str(raw.get("id") or "")
    location = (raw.get("location") or {}).get("display_name") or ""
    company = (raw.get("company") or {}).get("display_name") or ""
    description = str(raw.get("description") or "")
    url = raw.get("redirect_url")
    job = {
        "job_key": f"adzuna:{country}:{external_id}",
        "canonical_key": f"adzuna:{country}:{external_id}",
        "source": SOURCE,
        "board": country,
        "external_id": external_id,
        "company": company.strip(),
        "title": str(raw.get("title") or "").strip(),
        "location": location,
        "work_mode": "remote" if "remote" in (location + " " + description).lower() else None,
        "employment_type": raw.get("contract_time") or None,
        "description": description[:12000],
        "url": url,
        # An aggregator link is a redirect to whoever actually holds the posting,
        # so this is a handoff by nature and never a form we could fill.
        "apply": {"kind": "external", "url": url},
        "published_at": raw.get("created"),
        "updated_at": raw.get("created"),
        "departments": [c for c in [(raw.get("category") or {}).get("label")] if c],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def _credentials() -> tuple[str, str]:
    from ..config import settings as cfg

    s = cfg()
    app_id, app_key = s.adzuna_app_id, s.adzuna_app_key
    if not app_id or not app_key:
        raise ValueError("adzuna needs ADZUNA_APP_ID and ADZUNA_APP_KEY")
    return app_id, app_key


def _query(country: str, query: str, page: int, per_page: int) -> str:
    app_id, app_key = _credentials()
    params = {"app_id": app_id, "app_key": app_key, "results_per_page": per_page,
              "content-type": "application/json"}
    if query:
        params["what"] = query
    return f"{BASE}/{country}/search/{page}?{urllib.parse.urlencode(params)}"


def fetch_board(spec: str, *, pages: int = 3, per_page: int = 50) -> list[dict]:
    country, query = parse_spec(spec)
    jobs: list[dict] = []
    for page in range(1, pages + 1):
        data: Any = fetch_json(_query(country, query, page, per_page), HOSTS, timeout=25)
        found = data.get("results") if isinstance(data, dict) else None
        if not found:
            break
        jobs.extend(normalize(country, j) for j in found if isinstance(j, dict) and j.get("title"))
        if len(found) < per_page:
            break
    return jobs


def search(spec: str, query: str, *, limit: int = 50) -> list[dict]:
    """Ask Adzuna to run the search, the same way the employer boards are asked."""
    country, preset = parse_spec(spec)
    data: Any = fetch_json(_query(country, query or preset, 1, max(1, min(50, limit))), HOSTS, timeout=25)
    found = data.get("results") if isinstance(data, dict) else None
    return [normalize(country, j) for j in (found or []) if isinstance(j, dict) and j.get("title")]
