"""Microsoft Careers public search.

Microsoft's careers UI calls these unauthenticated JSON endpoints. Search is
used on demand rather than mirrored into the scheduled corpus, so a user naming
Microsoft gets the employer's current results instead of a false "we don't
track them" answer.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from ..util import sha256
from .http import fetch_json

SOURCE = "microsoft-careers"
BASE = "https://apply.careers.microsoft.com"
HOSTS = {"apply.careers.microsoft.com"}


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _location(raw: dict) -> str:
    locs = raw.get("locations") or []
    vals: list[str] = []
    for loc in locs if isinstance(locs, list) else []:
        if isinstance(loc, str):
            vals.append(_clean(loc))
        elif isinstance(loc, dict):
            vals.append(_clean(loc.get("name") or loc.get("displayName") or loc.get("location")))
    return " | ".join(v for v in vals if v)


def normalize(raw: dict) -> dict:
    external_id = str(raw.get("id") or raw.get("positionId") or "")
    path = raw.get("positionUrl") or raw.get("url") or f"/careers/job/{external_id}"
    url = path if str(path).startswith("http") else BASE + str(path)
    title = _clean(raw.get("name") or raw.get("title"))
    location = _location(raw)
    description = _clean(raw.get("jobDescription") or raw.get("description"))
    job = {
        "job_key": f"microsoft:{external_id}",
        "canonical_key": f"microsoft:{external_id}",
        "source": SOURCE,
        "board": "microsoft.com",
        "external_id": external_id,
        "company": "Microsoft",
        "title": title,
        "location": location,
        "work_mode": "remote" if "remote" in location.lower() else None,
        "description": description[:12000],
        "url": url,
        "apply": {"kind": "external", "url": url},
        "published_at": raw.get("postedDate") or raw.get("created"),
        "updated_at": raw.get("updatedDate") or raw.get("created"),
        "departments": [],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def _detail(position_id: str) -> str:
    if not position_id:
        return ""
    params = urllib.parse.urlencode({"position_id": position_id, "domain": "microsoft.com", "hl": "en"})
    data: Any = fetch_json(f"{BASE}/api/pcsx/position_details?{params}", HOSTS,
                           headers={"Accept": "application/json", "Referer": BASE + "/"}, timeout=20)
    if not isinstance(data, dict):
        return ""
    body = data.get("data") or {}
    return _clean(body.get("jobDescription") or body.get("description"))


def search(query: str, *, location: str = "", limit: int = 50, hydrate: int = 12) -> list[dict]:
    """Ask Microsoft Careers directly and optionally hydrate top descriptions."""
    params = {
        "domain": "microsoft.com",
        "query": query or "software engineer",
        "start": 0,
    }
    if location:
        params["location"] = location
    data: Any = fetch_json(f"{BASE}/api/pcsx/search?{urllib.parse.urlencode(params)}", HOSTS,
                           headers={"Accept": "application/json", "Referer": BASE + "/"}, timeout=20)
    body = (data or {}).get("data") if isinstance(data, dict) else {}
    positions = (body or {}).get("positions") or []
    jobs = [normalize(p) for p in positions[:max(1, min(50, limit))]
            if isinstance(p, dict) and (p.get("name") or p.get("title"))]
    for job in jobs[:max(0, min(hydrate, len(jobs)))]:
        try:
            desc = _detail(job["external_id"])
        except Exception:
            desc = ""
        if desc:
            job["description"] = desc[:12000]
            job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return jobs
