"""Google Careers direct search from the public careers results page."""

from __future__ import annotations

import json
import re
import urllib.parse

from ..util import sha256
from .http import fetch

SOURCE = "google-careers"
BASE = "https://www.google.com/about/careers/applications/jobs/results/"
HOSTS = {"www.google.com"}

_DS1 = re.compile(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:", re.S)


def _extract(html: str) -> list:
    hit = _DS1.search(html)
    if not hit:
        return []
    start = hit.end()
    # Find the first array after data: and balance brackets. JSON is embedded
    # directly in the page; no execution or browser is required.
    start = html.find("[", start)
    if start < 0:
        return []
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(html[start:i + 1])
                except Exception:
                    return []
                return data[0] if data and isinstance(data[0], list) else []
    return []


def normalize(raw: list) -> dict | None:
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    external_id = str(raw[0] or "")
    title = str(raw[1] or "").strip()
    url = str(raw[2] or "").strip()
    if url and not url.startswith("http"):
        url = "https://www.google.com" + url
    locs = raw[9] if len(raw) > 9 and raw[9] else []
    locations = []
    for loc in locs if isinstance(locs, list) else []:
        if isinstance(loc, list) and loc and loc[0]:
            locations.append(str(loc[0]).strip())
        elif isinstance(loc, str):
            locations.append(loc.strip())
    location = " | ".join(x for x in locations if x)
    job = {
        "job_key": f"google:{external_id}",
        "canonical_key": f"google:{external_id}",
        "source": SOURCE,
        "board": "google.com",
        "external_id": external_id,
        "company": "Google",
        "title": title,
        "location": location,
        "work_mode": "remote" if "remote" in location.lower() else None,
        "description": "",
        "url": url,
        "apply": {"kind": "external", "url": url},
        "published_at": None,
        "updated_at": None,
        "departments": [],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def search(query: str, *, location: str = "", limit: int = 50) -> list[dict]:
    params = {"q": query or "software engineer"}
    if location:
        params["location"] = location
    url = BASE + "?" + urllib.parse.urlencode(params)
    _, raw, _ = fetch(url, HOSTS, headers={"Accept": "text/html"}, timeout=25)
    rows = _extract(raw.decode("utf8", "ignore"))
    jobs = []
    for row in rows:
        job = normalize(row)
        if job and job["title"]:
            jobs.append(job)
        if len(jobs) >= max(1, min(50, limit)):
            break
    return jobs
