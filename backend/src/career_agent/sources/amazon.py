"""Amazon Jobs.

amazon.jobs serves its own search as public JSON, unauthenticated - the same
request the site's own results page makes. It is the one employer here whose
listings carry a structured intern flag and separate basic and preferred
qualifications, which is exactly the shape the matcher wants: requirements that
were written as requirements rather than inferred from prose.

Configured as `COUNTRY` or `COUNTRY:query`, e.g. `IND` or `IND:intern`. The
country is applied by the API rather than after, so a search for Indian roles
does not pull the rest of the world first.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from ..util import sha256
from .http import fetch_json

SOURCE = "amazon-jobs"
HOSTS = {"amazon.jobs"}
SPEC_RE = re.compile(r"^([A-Za-z]{2,3})(?::([A-Za-z0-9 +#._-]{1,60}))?$")
BASE = "https://www.amazon.jobs/en/search.json"


def parse_spec(spec: str) -> tuple[str, str]:
    match = SPEC_RE.match((spec or "").strip())
    if not match:
        raise ValueError("amazon board must look like COUNTRY or COUNTRY:query, e.g. IND or IND:intern")
    return match.group(1).upper(), (match.group(2) or "").strip()


def _clean(text: str | None) -> str:
    return re.sub(r"\s{2,}", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def normalize(raw: dict) -> dict:
    external_id = str(raw.get("id_icims") or raw.get("id") or "")
    path = raw.get("job_path") or ""
    url = f"https://www.amazon.jobs{path}" if path.startswith("/") else "https://www.amazon.jobs/en/jobs/" + external_id
    location = _clean(raw.get("normalized_location") or raw.get("location"))
    description = "\n\n".join(p for p in (
        _clean(raw.get("description_short")) or _clean(raw.get("description")),
        ("Basic qualifications:\n" + _clean(raw["basic_qualifications"])) if raw.get("basic_qualifications") else "",
        ("Preferred qualifications:\n" + _clean(raw["preferred_qualifications"])) if raw.get("preferred_qualifications") else "",
    ) if p)
    job = {
        "job_key": f"amazon:{external_id}",
        "canonical_key": f"amazon:{external_id}",
        "source": SOURCE,
        "board": (raw.get("country_code") or "").upper(),
        "external_id": external_id,
        # company_name is the hiring legal entity - "ASSPL - Karnataka",
        # "Amazon Dev Centre India". Nobody searches for those, and showing them
        # makes an Amazon role look like an unknown company. The entity is kept
        # as the employer of record; the name people recognise is the company.
        "company": "Amazon",
        "legal_entity": raw.get("company_name") or None,
        "title": _clean(raw.get("title")),
        "location": location,
        "country": (raw.get("country_code") or "").upper() or None,
        "work_mode": "remote" if "virtual" in location.lower() or "remote" in location.lower() else None,
        # is_intern is documented but absent from the search response, so the
        # title is the fallback - "Financial Analyst Intern" is an internship
        # whatever the flag says.
        "employment_type": "internship" if raw.get("is_intern") or re.search(
            r"\bintern(ship)?\b", _clean(raw.get("title")), re.I) else None,
        "description": description[:12000],
        "url": url,
        # Submitting needs an Amazon candidate account, so this is a handoff.
        "apply": {"kind": "external", "url": url},
        "published_at": raw.get("posted_date"),
        "updated_at": raw.get("updated_time") or raw.get("posted_date"),
        "departments": [d for d in (raw.get("job_category"), raw.get("business_category")) if d],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def fetch_board(spec: str, *, pages: int = 4, per_page: int = 100) -> list[dict]:
    country, query = parse_spec(spec)
    jobs: list[dict] = []
    for page in range(pages):
        params = {"country": country, "result_limit": per_page, "offset": page * per_page, "sort": "recent"}
        if query:
            params["base_query"] = query
        data: Any = fetch_json(f"{BASE}?{urllib.parse.urlencode(params)}", HOSTS,
                               headers={"Accept": "application/json"}, timeout=25)
        found = data.get("jobs") if isinstance(data, dict) else None
        if not found:
            break
        jobs.extend(normalize(j) for j in found if isinstance(j, dict) and j.get("title"))
        if len(found) < per_page:
            break
    return jobs
