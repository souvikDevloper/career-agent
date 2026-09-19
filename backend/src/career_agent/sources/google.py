"""Google Careers direct search from the public careers results page."""

from __future__ import annotations

import json
import re
import urllib.parse

from ..util import sha256
from .http import FetchError, fetch

SOURCE = "google-careers"
BASE = "https://www.google.com/about/careers/applications/jobs/results"
HOSTS = {"www.google.com"}

_DS1 = re.compile(r"AF_initDataCallback\(\{key:\s*['\"]ds:1['\"].*?data\s*:", re.S)
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


_ROLE_ALIASES = {
    "swe": "software engineer",
    "sde": "software engineer",
}


def query_plan(query: str) -> tuple[str, str | None]:
    """Turn what a person/model says into the query Google Careers expects.

    Google understands "software engineer"; it does not reliably understand the
    shorthand "SWE". Seniority phrases such as "early career" are filters, not
    text that has to appear in the posting title. Keeping them in q caused a
    second failure after the direct search was added: Google returned live EARLY
    roles, then our own text filter rejected "Software Engineer, Search" because
    its title does not literally contain "early career".
    """
    raw = (query or "software engineer").strip().lower()
    raw = re.sub(r"\b(early|entry|new)[- ]+(career|careers|level|grad|graduate)\b", r"\1 \2", raw)
    level = None
    if re.search(r"\b(early careers?|new grad(?:uate)?s?|university graduates?|entry level)\b", raw, re.I):
        level = "EARLY"
    elif re.search(r"\b(interns?|internships?|apprentices?|intern and apprentice)\b", raw, re.I):
        level = "INTERN_AND_APPRENTICE"

    cleaned = re.sub(
        r"\b(early careers?|new grad(?:uate)?s?|university graduates?|entry level|"
        r"interns?|internships?|apprentices?|intern and apprentice|jobs?[a-z]?|roles?[a-z]?|openings?[a-z]?)\b",
        " ",
        raw,
        flags=re.I,
    )
    for short, full in _ROLE_ALIASES.items():
        cleaned = re.sub(rf"\b{re.escape(short)}\b", full, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or "software engineer"
    return cleaned, level


def post_filter_role(query: str) -> str:
    """Role text safe to re-apply after Google's server-side seniority filter."""
    cleaned, _ = query_plan(query)
    return cleaned


def _extract(html: str) -> list:
    hit = _DS1.search(html)
    if not hit:
        raise FetchError("google careers results payload was not present")
    start = hit.end()
    # Find the first array after data: and balance brackets. JSON is embedded
    # directly in the page; no execution or browser is required.
    start = html.find("[", start)
    if start < 0:
        raise FetchError("google careers results payload was malformed")
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
                except (ValueError, TypeError) as exc:
                    raise FetchError("google careers results payload was malformed") from exc
                if not isinstance(data, list) or not data or (data[0] is not None and not isinstance(data[0], list)):
                    raise FetchError("google careers results payload shape changed")
                return data[0] or []
    raise FetchError("google careers results payload was incomplete")


def _html_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _slug(title: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", title.lower()))


def normalize(raw: list) -> dict | None:
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    external_id = str(raw[0] or "").strip()
    title = str(raw[1] or "").strip()
    if not external_id or not title:
        return None

    # Google has changed the third slot more than once. The stable identity is
    # the numeric/string job id, so construct the canonical public URL from it
    # instead of trusting an incidental payload position.
    url = f"{BASE}/{external_id}-{_slug(title)}"

    locs = raw[9] if len(raw) > 9 and isinstance(raw[9], list) else []
    locations = []
    for loc in locs:
        if isinstance(loc, list) and loc and loc[0]:
            locations.append(str(loc[0]).strip())
        elif isinstance(loc, str) and loc.strip():
            locations.append(loc.strip())
    location = " | ".join(dict.fromkeys(locations))

    # The search payload carries enough of the posting to score it without an
    # extra request. Keep only the human-readable sections and strip markup.
    sections = []
    for idx in (10, 3, 4, 19):  # about, responsibilities, minimum, preferred
        if len(raw) > idx and isinstance(raw[idx], list) and len(raw[idx]) > 1:
            text = _html_text(raw[idx][1])
            if text:
                sections.append(text)
    description = "\n\n".join(sections)[:12000]

    company = str(raw[7] or "Google").strip() if len(raw) > 7 else "Google"
    published = None
    if len(raw) > 12 and isinstance(raw[12], list) and raw[12] and isinstance(raw[12][0], (int, float)):
        from datetime import datetime, timezone
        published = datetime.fromtimestamp(raw[12][0], tz=timezone.utc).isoformat(timespec="seconds")

    job = {
        "job_key": f"google:{external_id}",
        "canonical_key": f"google:{external_id}",
        "source": SOURCE,
        "board": "google.com",
        "external_id": external_id,
        "company": company or "Google",
        # Google Careers also publishes YouTube roles. Keep the displayed
        # employer while making searches for the parent careers board work.
        "company_aliases": ["Google"],
        "title": title,
        "location": location,
        "work_mode": "remote" if "remote" in (location + " " + description).lower() else None,
        "description": description,
        "url": url,
        "apply": {"kind": "external", "url": url},
        "published_at": published,
        "updated_at": published,
        "departments": [],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def search(query: str, *, location: str = "", limit: int = 50) -> list[dict]:
    cleaned_query, target_level = query_plan(query)
    wanted = max(1, min(50, limit))
    jobs = []
    seen = set()

    # Google exposes 20 rows per search page. Querying only page zero made a
    # direct search fragile: one odd first page or a slightly over-specific
    # query could be reported as "0 roles" even though later pages contained
    # valid India openings. Three pages is bounded and still cheap.
    for page in range(1, min(3, (wanted + 19) // 20) + 1):
        params = {"q": cleaned_query, "hl": "en", "sort_by": "date", "page": page}
        if location:
            params["location"] = location
        if target_level:
            params["target_level"] = target_level
        url = BASE + "?" + urllib.parse.urlencode(params)
        _, raw, _ = fetch(url, HOSTS, headers=_BROWSER_HEADERS, timeout=25)
        html = raw.decode("utf8", "ignore")
        rows = _extract(html)
        if not rows:
            break

        for row in rows:
            job = normalize(row)
            if job and job["title"] and job["job_key"] not in seen:
                seen.add(job["job_key"])
                jobs.append(job)
            if len(jobs) >= wanted:
                return jobs
        if rows and not any(normalize(row) for row in rows):
            raise FetchError("google careers returned rows that could not be read")
        if len(rows) < 20:
            break
    return jobs
