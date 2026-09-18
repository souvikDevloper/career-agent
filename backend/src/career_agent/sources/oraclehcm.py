"""Oracle Cloud recruiting (Oracle HCM) careers sites.

The other half of the large-employer world runs on Oracle rather than Workday -
JPMorgan Chase alone publishes over seven thousand openings this way. Every one
of those sites is a front end over the same documented REST resource its own
pages call, unauthenticated, no session.

Configured as `tenant:site` or `tenant:site:COUNTRY`, e.g. `jpmc:CX_1001:IN`.
The optional country is applied at ingestion rather than after, because pulling
seven thousand postings to keep the two hundred in one country is a lot of
writes for data nobody reads. Postings arrive newest first, which is what makes
a small page limit reasonable.
"""

from __future__ import annotations

import re
from typing import Any

from ..util import sha256
from .http import fetch_json

SOURCE = "oraclehcm-public"
HOSTS = {"oraclecloud.com"}
SPEC_RE = re.compile(r"^([a-z0-9][a-z0-9-]{1,40}):([A-Za-z0-9_]{1,40})(?::([A-Za-z]{2}))?$")


def parse_spec(spec: str) -> tuple[str, str, str | None]:
    match = SPEC_RE.match((spec or "").strip())
    if not match:
        raise ValueError("oracle board must look like tenant:site or tenant:site:COUNTRY, e.g. jpmc:CX_1001:IN")
    return match.group(1), match.group(2), (match.group(3) or "").upper() or None


def _text(raw: dict) -> str:
    parts = [raw.get("ShortDescriptionStr"), raw.get("ExternalResponsibilitiesStr"), raw.get("ExternalQualificationsStr")]
    joined = "\n\n".join(p for p in parts if p)
    return re.sub(r"\s{2,}", " ", re.sub(r"<[^>]+>", " ", joined)).strip()[:12000]


def normalize(tenant: str, site: str, raw: dict) -> dict:
    external_id = str(raw.get("Id") or "")
    location = (raw.get("PrimaryLocation") or "").strip()
    workplace = (raw.get("WorkplaceType") or "").strip().lower()
    mode = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on-site": "onsite"}.get(workplace)
    job = {
        "job_key": f"oraclehcm:{tenant}:{external_id}",
        "canonical_key": f"oraclehcm:{tenant}:{external_id}",
        "source": SOURCE,
        "board": f"{tenant}:{site}",
        "external_id": external_id,
        "company": tenant.replace("-", " ").upper() if len(tenant) <= 4 else tenant.replace("-", " ").title(),
        "title": (raw.get("Title") or "").strip(),
        "location": location,
        "country": raw.get("PrimaryLocationCountry"),
        "work_mode": mode or ("remote" if "remote" in location.lower() else None),
        "employment_type": (raw.get("JobType") or raw.get("WorkerType") or "").lower() or None,
        "description": _text(raw),
        "url": f"https://{tenant}.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/{site}/job/{external_id}",
        "apply": {"kind": "external",
                  "url": f"https://{tenant}.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/{site}/job/{external_id}"},
        "published_at": raw.get("PostedDate"),
        "updated_at": raw.get("PostedDate"),
        "departments": [d for d in (raw.get("JobFamily"), raw.get("JobFunction")) if d],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def fetch_board(spec: str, *, pages: int = 3, per_page: int = 200) -> list[dict]:
    tenant, site, country = parse_spec(spec)
    jobs: list[dict] = []
    for page in range(pages):
        finder = (f"findReqs;siteNumber={site},limit={per_page},offset={page * per_page},"
                  "sortBy=POSTING_DATES_DESC")
        url = (f"https://{tenant}.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
               f"?onlyData=true&expand=requisitionList&finder={finder}")
        data: Any = fetch_json(url, HOSTS, headers={"Accept": "application/json"}, timeout=25)
        items = data.get("items") if isinstance(data, dict) else None
        if not items:
            break
        postings = items[0].get("requisitionList") or []
        if not postings:
            break
        for raw in postings:
            if not isinstance(raw, dict) or not raw.get("Title"):
                continue
            if country and (raw.get("PrimaryLocationCountry") or "").upper() != country:
                continue
            jobs.append(normalize(tenant, site, raw))
        if len(postings) < per_page:
            break
    return jobs
