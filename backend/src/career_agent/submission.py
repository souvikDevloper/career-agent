"""Submission strategy planning.

One connector can expose several application surfaces. The strategy therefore
belongs to the concrete job, not to a connector-wide capability flag.

Cloud submission is reserved for forms this service can actually reach and fill
without a user account. Authenticated employer portals use the user's browser:
the backend still prepares and validates the packet, but submission waits for a
local/browser companion instead of pretending the job is unsupported.
"""

from __future__ import annotations

from urllib.parse import urlparse

from . import connectors

LOCAL_BROWSER_CONNECTORS = {
    "amazon-jobs",
    "microsoft-careers",
    "google-careers",
    "workday-public",
    "lever-public",
    "ashby-public",
    "oraclehcm-public",
    "linkedin",
}


def submission_plan(job: dict, connector: str | None = None) -> dict:
    connector = connector or job.get("connector") or job.get("source") or ""
    apply = job.get("apply") or {}
    url = apply.get("url") or job.get("url")
    kind = apply.get("kind")
    # Existing cached Amazon jobs may still carry the public posting URL from
    # before the authenticated-browser executor existed. Derive the stable
    # application route from the job id so re-prepare fixes old records too.
    if connector == "amazon-jobs" and job.get("external_id"):
        url = f"https://account.amazon.jobs/en-US/applicant/jobs/{job['external_id']}/apply"
    host = ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except (ValueError, TypeError, AttributeError):
        host = ""

    if connector == "northwind-test-portal":
        return {
            "mode": "cloud_browser",
            "can_fill": True,
            "can_submit": True,
            "requires_user_presence": False,
            "requires_login": False,
            "url": url,
            "reason": "test employer form is directly reachable by the browser worker",
        }

    if connector == "greenhouse-public" and kind == "hosted_form" and (
        host == "job-boards.greenhouse.io" or host.endswith(".job-boards.greenhouse.io")
    ):
        return {
            "mode": "cloud_browser",
            "can_fill": True,
            "can_submit": True,
            "requires_user_presence": False,
            "requires_login": False,
            "url": url,
            "reason": "the posting is hosted on Greenhouse's public application form",
        }

    if connector in LOCAL_BROWSER_CONNECTORS or kind == "external":
        return {
            "mode": "local_browser",
            "can_fill": True,
            "can_submit": True,
            "requires_user_presence": True,
            "requires_login": True,
            "url": url,
            "reason": "submission needs the user's authenticated browser session",
        }

    return {
        "mode": "manual",
        "can_fill": False,
        "can_submit": False,
        "requires_user_presence": True,
        "requires_login": False,
        "url": url,
        "reason": connectors.CONNECTORS.get(connector, {}).get("note") or "no supported submission route",
    }


def can_cloud_submit(job: dict, connector: str | None = None) -> bool:
    plan = submission_plan(job, connector)
    return plan["mode"] == "cloud_browser" and bool(plan["can_submit"])
