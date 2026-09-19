"""Microsoft Careers public search.

Microsoft's careers UI calls these unauthenticated JSON endpoints. Search is
used on demand rather than mirrored into the scheduled corpus, so a user naming
Microsoft gets the employer's current results instead of a false "we don't
track them" answer.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from ..util import sha256
from .google import query_plan
from .http import FetchError, fetch_json

SOURCE = "microsoft-careers"
BASE = "https://apply.careers.microsoft.com"
HOSTS = {"apply.careers.microsoft.com"}
HEADERS = {"Accept": "application/json", "Referer": BASE + "/careers",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"}


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text or ""))).strip()


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
    posted = raw.get("postedDate") or raw.get("created")
    if not posted and isinstance(raw.get("postedTs"), (int, float)):
        posted = datetime.fromtimestamp(raw["postedTs"], timezone.utc).isoformat(timespec="seconds")
    job = {
        "job_key": f"microsoft:{external_id}",
        "canonical_key": f"microsoft:{external_id}",
        "source": SOURCE,
        "board": "microsoft.com",
        "external_id": external_id,
        "company": "Microsoft",
        "title": title,
        "location": location,
        "work_mode": raw.get("workLocationOption") or ("remote" if "remote" in location.lower() else None),
        "description": description[:12000],
        "url": url,
        "apply": {"kind": "external", "url": url},
        "published_at": posted,
        "updated_at": raw.get("updatedDate") or raw.get("created"),
        "departments": [],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def _detail(position_id: str, *, timeout: float = 10) -> str:
    if not position_id:
        return ""
    params = urllib.parse.urlencode({"position_id": position_id, "domain": "microsoft.com", "hl": "en"})
    data: Any = fetch_json(f"{BASE}/api/pcsx/position_details?{params}", HOSTS,
                           headers=HEADERS, timeout=timeout)
    if not isinstance(data, dict):
        return ""
    body = data.get("data") or {}
    return _clean(body.get("jobDescription") or body.get("description"))


def search(query: str, *, location: str = "", limit: int = 50, hydrate: int = 0) -> list[dict]:
    """Ask Microsoft Careers directly and optionally hydrate top descriptions."""
    cleaned, level = query_plan(query)
    params = {
        "domain": "microsoft.com",
        "query": cleaned,
        "start": 0,
    }
    if level:
        params["filter_seniority"] = "Entry" if level == "EARLY" else "Intern"
    if location:
        params["location"] = location
    wanted = max(1, min(50, limit))
    jobs: list[dict] = []
    seen: set[str] = set()
    for _ in range(5):
        data: Any = fetch_json(f"{BASE}/api/pcsx/search?{urllib.parse.urlencode(params)}", HOSTS,
                               headers=HEADERS, timeout=15)
        body = data.get("data") if isinstance(data, dict) else None
        if not isinstance(body, dict) or not isinstance(body.get("positions"), list):
            raise FetchError("microsoft careers search returned an unreadable response")
        positions = body["positions"]
        added = 0
        for position in positions:
            if not isinstance(position, dict) or not (position.get("name") or position.get("title")):
                continue
            job = normalize(position)
            if job["job_key"] not in seen:
                seen.add(job["job_key"])
                jobs.append(job)
                added += 1
        if len(jobs) >= wanted or not added or len(positions) < 10:
            break
        params["start"] += len(positions)
        if isinstance(body.get("count"), int) and params["start"] >= body["count"]:
            break
    jobs = jobs[:wanted]
    for job in jobs[:max(0, min(hydrate, len(jobs)))]:
        try:
            desc = _detail(job["external_id"])
        except Exception:
            desc = ""
        if desc:
            job["description"] = desc[:12000]
            job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return jobs
