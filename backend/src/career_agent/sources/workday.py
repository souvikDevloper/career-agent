"""Workday-hosted careers sites.

Most large employers run their careers site on Workday, and every one of those
sites is a front-end over the same public JSON search its own pages call. No
key, no session, no login - the same request a visitor's browser makes. That is
what makes this fair game where a site that blocks non-browser clients is not.

One tenant, one connector instance: PayPal, NVIDIA, Salesforce and Adobe all
answer the same shape at different hostnames.

The listing returns a title, a location string and a path; the description
lives behind a second call per posting. Fetching hundreds of those on every
poll would be rude and slow, so descriptions are pulled only for the postings
that survive keyword filtering, and `description` is empty until then. The
scorer already treats a missing description as missing evidence rather than
inventing any.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..util import sha256
from .http import fetch, fetch_json

SOURCE = "workday-public"
TENANT_RE = r"[a-z0-9][a-z0-9-]{1,40}"
POD_RE = r"wd\d{1,3}"
SITE_RE = r"[A-Za-z0-9_-]{1,60}"
HOSTS = {"myworkdayjobs.com"}

# Tenants are configured as "tenant:pod:site", e.g. "paypal:wd1:jobs".
SPEC_RE = re.compile(rf"^({TENANT_RE}):({POD_RE}):({SITE_RE})$")


def parse_spec(spec: str) -> tuple[str, str, str]:
    match = SPEC_RE.match((spec or "").strip())
    if not match:
        raise ValueError("workday board must look like tenant:pod:site, e.g. paypal:wd1:jobs")
    return match.group(1), match.group(2), match.group(3)


def _company(tenant: str) -> str:
    return tenant.replace("-", " ").title()


def normalize(tenant: str, pod: str, site: str, raw: dict) -> dict:
    path = raw.get("externalPath") or ""
    # bulletFields carries the requisition number the employer shows publicly.
    bullets = [b for b in (raw.get("bulletFields") or []) if isinstance(b, str)]
    external_id = bullets[0] if bullets else path.rsplit("_", 1)[-1] or path
    location = (raw.get("locationsText") or "").strip()
    job = {
        "job_key": f"workday:{tenant}:{external_id}",
        "canonical_key": f"workday:{tenant}:{external_id}",
        "source": SOURCE,
        "board": f"{tenant}:{pod}:{site}",
        "external_id": str(external_id),
        "company": _company(tenant),
        "title": (raw.get("title") or "").strip(),
        "location": location,
        # Workday has no structured work-mode field; scoring reads the location text.
        "work_mode": "remote" if "remote" in location.lower() else None,
        "employment_type": None,
        # Filled in later, only for postings that survive filtering.
        "description": "",
        "url": f"https://{tenant}.{pod}.myworkdayjobs.com/en-US/{site}{path}",
        "apply": {"kind": "external", "url": f"https://{tenant}.{pod}.myworkdayjobs.com/en-US/{site}{path}"},
        "published_at": raw.get("postedOn"),
        "updated_at": raw.get("postedOn"),
        "departments": [],
        "requirements": None,
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def fetch_board(spec: str, *, pages: int = 5, per_page: int = 20) -> list[dict]:
    """Paged listing, newest first.

    Workday rejects a page larger than 20 with a bare 400, so the page size is
    the server's limit rather than a tuning knob. Five pages is a deliberate
    stop: twenty tenants polled in one run, and the scheduler has to finish.
    """
    tenant, pod, site = parse_spec(spec)
    url = f"https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    jobs: list[dict] = []
    total = 0
    for page in range(pages):
        body = json.dumps({"appliedFacets": {}, "limit": per_page,
                           "offset": page * per_page, "searchText": ""}).encode()
        data: Any = fetch_json(url, HOSTS, method="POST", body=body,
                               headers={"Content-Type": "application/json", "Accept": "application/json"},
                               timeout=25)
        postings = data.get("jobPostings") if isinstance(data, dict) else None
        if not postings:
            break
        # Workday reports the total on the first page and sends 0 on every page
        # after it. Re-reading it each time made "have we got them all?" true
        # immediately, which stopped every tenant at two pages.
        total = total or int(data.get("total") or 0)
        jobs.extend(normalize(tenant, pod, site, p) for p in postings if isinstance(p, dict) and p.get("title"))
        if len(postings) < per_page or (total and len(jobs) >= total):
            break
    return jobs


def fetch_description(job: dict) -> str:
    """Pull one posting's description. Called for filtered candidates only."""
    board = job.get("board") or ""
    try:
        tenant, pod, site = parse_spec(board)
    except ValueError:
        return ""
    path = (job.get("url") or "").split(f"/en-US/{site}", 1)[-1]
    if not path.startswith("/"):
        return ""
    url = f"https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}"
    try:
        _, raw, _ = fetch(url, HOSTS, headers={"Accept": "application/json"}, timeout=20)
        info = json.loads(raw.decode("utf8")).get("jobPostingInfo") or {}
    except Exception:
        return ""
    text = re.sub(r"<[^>]+>", " ", info.get("jobDescription") or "")
    return re.sub(r"\s{2,}", " ", text).strip()[:12000]
