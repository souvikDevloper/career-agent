"""Connector capability registry.

A connected identity is not evidence that a capability exists. Every connector
declares exactly what it can do and in which environment, and the UI renders
that status verbatim (verified live / test environment / needs setup / manual handoff).
"""

from __future__ import annotations

CAPABILITIES = ("discover", "read_details", "read_form", "fill", "submit", "reconcile",
                "read_messages", "send_messages", "update_profile")

CONNECTORS: dict[str, dict] = {
    "northwind-test-portal": {
        "label": "Northwind Labs careers (test employer)",
        "environment": "test",
        "status": "test_environment",
        "capabilities": ["discover", "read_details", "read_form", "fill", "submit", "reconcile", "read_messages"],
        "note": "A separately hosted test employer portal. Real form, real browser submission, real receipts. Not a real company.",
    },
    "greenhouse-public": {
        "label": "Greenhouse public job boards",
        "environment": "live",
        "status": "verified_live",
        "capabilities": ["discover", "read_details", "read_form", "fill", "submit"],
        "note": "Public GET endpoints need no key, and each job publishes its real application form - every field, type and required flag - so a packet is checked against the form the employer will actually receive. The submission API needs the employer's own Job Board key, so filing goes through the form itself.",
    },
    "lever-public": {"label": "Lever public job boards", "environment": "live", "status": "verified_live",
                     "capabilities": ["discover", "read_details"],
                     "note": "Public postings endpoint. Submitting needs the employer's key, so applying is a prepared manual handoff."},
    "amazon-jobs": {
        "label": "Amazon Jobs",
        "environment": "live", "status": "verified_live",
        "capabilities": ["discover", "read_details"],
        "note": ("amazon.jobs serves its own search as public JSON. The only board here that publishes "
                 "basic and preferred qualifications separately, which is the shape the matcher wants. "
                 "Submitting needs an Amazon candidate account, so applying is a prepared manual handoff."),
    },
    "oraclehcm-public": {
        "label": "Oracle HCM careers sites (JPMorgan Chase)",
        "environment": "live", "status": "verified_live",
        "capabilities": ["discover", "read_details"],
        "note": ("The documented public recruiting resource each employer's own careers page calls. "
                 "Supports filtering by country at ingestion. Submitting needs an account with the "
                 "employer, so applying is a prepared manual handoff."),
    },
    "workday-public": {
        "label": "Workday careers sites (PayPal, NVIDIA, Salesforce, Adobe, Autodesk, HP)",
        "environment": "live", "status": "verified_live",
        "capabilities": ["discover", "read_details"],
        "note": ("The same public JSON search each employer's own careers page calls - no key and no session. "
                 "Submitting needs an account with that employer, so applying is a prepared manual handoff."),
    },
    "ashby-public": {"label": "Ashby public job boards", "environment": "live", "status": "verified_live",
                     "capabilities": ["discover", "read_details"],
                     "note": "Public job board endpoint. Submitting needs the employer's key, so applying is a prepared manual handoff."},
    "email-ses": {
        "label": "Email (Amazon SES)",
        "environment": "live",
        "status": "needs_setup",
        "capabilities": ["send_messages"],
        "note": "SES sandbox delivers only to verified recipients until production access is granted.",
    },
    "telegram": {
        "label": "Telegram bot",
        "environment": "live",
        "status": "needs_setup",
        "capabilities": ["send_messages", "read_messages"],
        "note": "Link your chat with /start <code> to receive updates and approve applications.",
    },
    "gmail": {
        "label": "Gmail replies",
        "environment": "live",
        "status": "needs_setup",
        "capabilities": [],
        "note": "Reading Gmail needs restricted OAuth scopes and Google verification. Not enabled in this release.",
    },
    "linkedin": {
        "label": "LinkedIn",
        "environment": "live",
        "status": "manual_handoff",
        "capabilities": [],
        "note": "LinkedIn prohibits unauthorized automation. We prepare drafts and links; you act on LinkedIn yourself.",
    },
}


def can(connector: str, capability: str) -> bool:
    return capability in CONNECTORS.get(connector, {}).get("capabilities", [])


def environment(connector: str) -> str:
    return CONNECTORS.get(connector, {}).get("environment", "live")
