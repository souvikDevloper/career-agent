"""Northwind Labs careers — a separately deployed TEST EMPLOYER portal.

It exists so the product can demonstrate real discovery, real form reading, a real
browser submission and a real receipt without pretending to integrate with a real
employer. Every page carries a visible test-environment banner.
"""

from __future__ import annotations

import base64
import html
import json
import re
import secrets
from email.parser import BytesParser
from email.policy import default as email_policy
from typing import Any

from ..config import settings as cfg
from ..demo import PORTAL_SEED_JOBS, PUBLISHABLE_TEMPLATES
from ..store import C, DynamoStore, Put
from ..util import Clock, get_logger, log, new_id
from .common import verify_signature

logger = get_logger("portal")
_store = None
clock = Clock()

COMPANY = "Northwind Labs"


def store():
    global _store
    if _store is None:
        _store = DynamoStore(cfg().table_name)
    return _store


def base_url(event: dict) -> str:
    return cfg().api_base_url.rstrip("/") or f"https://{event.get('requestContext', {}).get('domainName', '')}"


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


def ensure_seed() -> None:
    if store().get("PORTAL#META", "SEED"):
        return
    now = clock.iso()
    for i, tpl in enumerate(PORTAL_SEED_JOBS):
        job_id = f"nw-{100 + i}"
        store().put({"pk": "PORTAL#JOBS", "sk": job_id, "id": job_id, "requisition_id": f"REQ-{2400 + i}", **tpl,
                     "published_at": now, "updated_at": now, "status": "open", "published_by": "seed"}, C("pk", "not_exists"))
    store().put({"pk": "PORTAL#META", "sk": "SEED", "at": now})


def jobs(include_closed: bool = False) -> list[dict]:
    rows = store().query("PORTAL#JOBS", "", limit=200)
    return [r for r in rows if include_closed or r.get("status") == "open"]


def job_json(event: dict, j: dict) -> dict:
    b = base_url(event)
    return {"id": j["id"], "requisition_id": j["requisition_id"], "company": COMPANY, "title": j["title"], "location": j["location"],
            "work_mode": j.get("work_mode"), "team": j.get("team"), "description": j["description"], "requirements": j.get("requirements"),
            "salary_min": j.get("salary_min"), "salary_max": j.get("salary_max"), "published_at": j["published_at"],
            "updated_at": j.get("updated_at"), "url": f"{b}/portal/jobs/{j['id']}", "apply_url": f"{b}/portal/jobs/{j['id']}/apply",
            "published_by": j.get("published_by"), "test_environment": True}


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CSS = """
:root{--ink:#0b2a22;--muted:#4b635b;--brand:#0f7b5f;--brand2:#12a37c;--bg:#f5faf7;--card:#fff;--line:#d9e7e1;--warn:#fff4d6;--warnink:#7a5200}
*{box-sizing:border-box}body{margin:0;font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
.test{background:var(--warn);color:var(--warnink);text-align:center;padding:8px 12px;font-weight:600;font-size:13px;border-bottom:1px solid #f1d58a}
header{background:linear-gradient(120deg,#0b3d2e,#0f7b5f);color:#fff;padding:28px 16px 36px}
.wrap{max-width:880px;margin:0 auto;padding:0 16px}.logo{display:flex;gap:10px;align-items:center;font-weight:800;letter-spacing:.2px}
.logo i{width:30px;height:30px;border-radius:9px;background:#fff;display:inline-grid;place-items:center;color:var(--brand);font-style:normal}
h1{font-size:30px;margin:18px 0 6px}header p{margin:0;opacity:.85}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:14px 0;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.job{display:flex;justify-content:space-between;gap:12px;align-items:center;text-decoration:none;color:inherit}
.job:hover{border-color:var(--brand2)}.meta{color:var(--muted);font-size:13px}.pill{background:#e7f5ef;color:var(--brand);border-radius:99px;padding:2px 10px;font-size:12px;font-weight:600}
label{display:block;font-weight:600;margin:14px 0 6px}input,select,textarea{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:10px;font:inherit;background:#fff}
input[type=checkbox]{width:auto}textarea{min-height:120px}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
button,.btn{background:var(--brand);color:#fff;border:0;border-radius:10px;padding:12px 18px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}
.check{display:flex;gap:10px;align-items:flex-start;font-weight:500}.check label{margin:0;font-weight:500}
.receipt{font-size:26px;font-weight:800;letter-spacing:1px;color:var(--brand)}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}
@media(max-width:640px){.row{grid-template-columns:1fr}h1{font-size:24px}}
"""


def page(title: str, body: str, sub: str = "Build the rails for India's next billion payments.") -> dict:
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · {COMPANY} Careers (test)</title><meta name="robots" content="noindex"><style>{CSS}</style></head>
<body><div class="test" role="note">TEST ENVIRONMENT — {COMPANY} is a fictional employer used to demonstrate Career Agent. No real hiring happens here.</div>
<header><div class="wrap"><div class="logo"><i>N</i>{COMPANY} Careers</div><h1>{html.escape(title)}</h1><p>{html.escape(sub)}</p></div></header>
<main class="wrap">{body}</main><footer class="wrap meta" style="padding:30px 16px">Fictional test employer · <a href="/portal">All openings</a> · <a href="/portal/employer">Employer console</a></footer></body></html>"""
    return {"statusCode": 200, "headers": {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                                           "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex"}, "body": doc}


def h(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


def list_page(event: dict) -> dict:
    cards = "".join(
        f"<a class='card job' href='/portal/jobs/{h(j['id'])}'><div><div style='font-weight:700;font-size:17px'>{h(j['title'])}</div>"
        f"<div class='meta'>{h(j.get('team'))} · {h(j['location'])} · posted {h(j['published_at'][:16].replace('T', ' '))} UTC</div></div>"
        f"<span class='pill'>{h((j.get('work_mode') or '').title())}</span></a>"
        for j in sorted(jobs(), key=lambda x: x["published_at"], reverse=True))
    return page("Open roles", cards or "<p>No open roles.</p>")


def detail_page(job: dict) -> dict:
    req = job.get("requirements") or {}
    skills = "".join(f"<li>{h(s)}</li>" for s in req.get("required_skills", []))
    nice = "".join(f"<li>{h(s)}</li>" for s in req.get("preferred_skills", []))
    resp = "".join(f"<li>{h(s)}</li>" for s in req.get("responsibilities", []))
    grad = ", ".join(str(y) for y in req.get("graduation_years", [])) or "Any"
    years = f"{req['min_years']}+ years" if req.get("min_years") else "Students and new graduates"
    body = f"""<div class="card"><div class="meta">{h(job.get('team'))} · {h(job['location'])} · Requisition {h(job['requisition_id'])}</div>
<p>{h(job['description'])}</p><h3>What you'll do</h3><ul>{resp}</ul><h3>Must have</h3><ul>{skills}</ul><h3>Nice to have</h3><ul>{nice}</ul>
<p class="meta">Experience: {h(years)} · Eligible graduation years: {h(grad)} · Stipend ₹{h(job.get('salary_min'))}–₹{h(job.get('salary_max'))}/month</p>
<a class="btn" href="/portal/jobs/{h(job['id'])}/apply">Apply now</a></div>"""
    return page(job["title"], body, f"{job.get('team')} · {job['location']}")


def apply_page(job: dict, errors: list[str] | None = None) -> dict:
    years = "".join(f"<option value='{y}'>{y}</option>" for y in range(2024, 2031))
    err = "".join(f"<li>{h(e)}</li>" for e in errors or [])
    body = f"""<div class="card">{'<ul style="color:#b42318">' + err + '</ul>' if err else ''}
<form id="application-form" method="post" action="/portal/jobs/{h(job['id'])}/apply" enctype="multipart/form-data">
<div class="row"><div><label for="first_name">First name *</label><input id="first_name" name="first_name" required autocomplete="given-name"></div>
<div><label for="last_name">Last name *</label><input id="last_name" name="last_name" required autocomplete="family-name"></div></div>
<div class="row"><div><label for="email">Email *</label><input id="email" name="email" type="email" required></div>
<div><label for="phone">Phone *</label><input id="phone" name="phone" type="tel" required></div></div>
<label for="resume">Resume (PDF or DOCX, max 2 MB) *</label><input id="resume" name="resume" type="file" accept=".pdf,.docx" required>
<div class="row"><div><label for="linkedin">LinkedIn profile</label><input id="linkedin" name="linkedin" type="url"></div>
<div><label for="github">GitHub profile</label><input id="github" name="github" type="url"></div></div>
<div class="row"><div><label for="university">University / College *</label><input id="university" name="university" required></div>
<div><label for="graduation_year">Graduation year *</label><select id="graduation_year" name="graduation_year" required><option value="">Select</option>{years}</select></div></div>
<label for="work_authorization">Are you legally authorized to work in India? *</label>
<select id="work_authorization" name="work_authorization" required><option value="">Select</option><option value="yes">Yes</option><option value="no">No</option></select>
<label for="start_date">Earliest start date *</label><input id="start_date" name="start_date" type="date" required>
<label for="why_northwind">Why do you want to join Northwind Labs? *</label><textarea id="why_northwind" name="why_northwind" required maxlength="3000"></textarea>
<label for="gender">Gender (optional)</label><select id="gender" name="gender"><option value="">Select</option><option value="female">Female</option>
<option value="male">Male</option><option value="non_binary">Non-binary</option><option value="decline">Decline to self-identify</option></select>
<div class="check" style="margin-top:16px"><input id="accuracy" name="accuracy" type="checkbox" value="yes" required>
<label for="accuracy">I confirm the information in this application is accurate</label></div>
<p style="margin-top:18px"><button id="submit-application" type="submit">Submit application</button></p></form></div>"""
    return page(f"Apply: {job['title']}", body, f"{job.get('team')} · {job['location']}")


REQUIRED = ["first_name", "last_name", "email", "phone", "university", "graduation_year", "work_authorization", "start_date",
            "why_northwind", "accuracy"]


def parse_multipart(event: dict) -> tuple[dict, dict]:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    ctype = headers.get("content-type", "")
    raw = event.get("body") or ""
    data = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("latin-1", "ignore")
    if len(data) > 3 * 1024 * 1024:
        raise ValueError("Upload too large (max 2 MB resume).")
    if "multipart/form-data" not in ctype:
        raise ValueError("Unsupported form encoding.")
    msg = BytesParser(policy=email_policy).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + data)
    fields: dict[str, str] = {}
    files: dict[str, dict] = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = {"filename": filename, "data": payload, "content_type": part.get_content_type()}
        else:
            fields[name] = payload.decode("utf8", "ignore").strip()
    return fields, files


def submit(event: dict, job: dict) -> dict:
    try:
        fields, files = parse_multipart(event)
    except ValueError as exc:
        return apply_page(job, [str(exc)])
    errors = [f"{k.replace('_', ' ').title()} is required." for k in REQUIRED if not fields.get(k)]
    email = fields.get("email", "").lower()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors.append("Enter a valid email.")
    resume = files.get("resume")
    if not resume or not resume["data"]:
        errors.append("Resume is required.")
    elif len(resume["data"]) > 2 * 1024 * 1024 or not (resume["data"].startswith(b"%PDF") or resume["data"].startswith(b"PK\x03\x04")):
        errors.append("Resume must be a PDF or DOCX under 2 MB.")
    if errors:
        return apply_page(job, errors)
    existing = store().get(f"PORTAL#APP#{job['id']}", f"EMAIL#{email}")
    if existing:
        return receipt_page(job, existing, duplicate=True)
    reference = "NWL-" + secrets.token_hex(3).upper()
    key = f"portal-applications/{job['id']}/{reference}.{'pdf' if resume['data'].startswith(b'%PDF') else 'docx'}"
    import boto3

    boto3.client("s3").put_object(Bucket=cfg().bucket, Key=key, Body=resume["data"], ServerSideEncryption="AES256")
    record = {"pk": f"PORTAL#APP#{job['id']}", "sk": f"EMAIL#{email}", "reference": reference, "job_id": job["id"],
              "job_title": job["title"], "submitted_at": clock.iso(), "resume_key": key, "resume_bytes": len(resume["data"]),
              "fields": {k: v[:3000] for k, v in fields.items()}, "gsi1pk": "PORTAL#APPLICATIONS", "gsi1sk": clock.iso(),
              "ttl": int(clock.now()) + 30 * 86400}
    try:
        store().put(record, C("pk", "not_exists"))
    except Exception as exc:
        if type(exc).__name__ != "ConditionFailed":
            raise
        record = store().get(f"PORTAL#APP#{job['id']}", f"EMAIL#{email}") or record
        return receipt_page(job, record, duplicate=True)
    log(logger, "portal.application_received", job=job["id"], reference=reference)
    return receipt_page(job, record)


def receipt_page(job: dict, record: dict, duplicate: bool = False) -> dict:
    note = "We already had your application for this role; here is the original receipt." if duplicate else "Application received."
    body = f"""<div class="card" id="receipt" data-reference="{h(record['reference'])}" data-submitted-at="{h(record['submitted_at'])}">
<p>{h(note)}</p><div class="meta">Reference</div><div class="receipt" id="receipt-reference">{h(record['reference'])}</div>
<p class="meta">Role: {h(job['title'])} · Received {h(record['submitted_at'])} UTC</p></div>"""
    return page("Thank you for applying", body, "We review every application within 5 working days (fictionally).")


def mask(name: str) -> str:
    return (name[:1] + "•••") if name else ""


def employer_page() -> dict:
    rows = store().query("PORTAL#APPLICATIONS", "", index="gsi1", limit=50, newest_first=True)
    trs = "".join(f"<tr><td>{h(r['reference'])}</td><td>{h(mask(r['fields'].get('first_name', '')))} {h(mask(r['fields'].get('last_name', '')))}</td>"
                  f"<td>{h(r['job_title'])}</td><td>{h(r['submitted_at'])}</td></tr>" for r in rows)
    body = f"<div class='card'><p class='meta'>Latest applications received by the test employer (names masked).</p><table><tr><th>Reference</th><th>Applicant</th><th>Role</th><th>Received (UTC)</th></tr>{trs}</table></div>"
    return page("Employer console", body, "What the (fictional) recruiter sees.")


# ---------------------------------------------------------------------------
# admin API (HMAC-signed calls from the Career Agent backend)
# ---------------------------------------------------------------------------


def admin_publish(body: dict) -> dict:
    tpl = next((t for t in PUBLISHABLE_TEMPLATES if t["slug"] == body.get("template")), None)
    if tpl is None:
        return _json(400, {"error": "unknown template"})
    n = new_id()[-6:]
    job_id = f"nw-{tpl['slug']}-{n}"
    now = clock.iso()
    item = {"pk": "PORTAL#JOBS", "sk": job_id, "id": job_id, "requisition_id": f"REQ-{tpl['slug'].upper()}-{n}", **tpl,
            "published_at": now, "updated_at": now, "status": "open", "published_by": str(body.get("published_by", "demo"))[:40],
            "ttl": int(clock.now()) + 3 * 86400}
    store().put(item, C("pk", "not_exists"))
    return _json(201, {"job": item})


def admin_reply(event: dict, body: dict) -> dict:
    """Recruiter sends a message about an application; delivered to Career Agent's inbound webhook."""
    import urllib.request

    from .common import portal_signature

    reference = body.get("reference")
    kind = body.get("kind")
    rows = store().query("PORTAL#APPLICATIONS", "", index="gsi1", limit=500, newest_first=True)
    rec = next((r for r in rows if r.get("reference") == reference), None)
    if not rec:
        return _json(404, {"error": "application not found"})
    first = rec["fields"].get("first_name", "there")
    deadline = clock.iso(clock.now() + 3 * 86400)
    templates = {
        "assessment": (f"Online assessment for {rec['job_title']}",
                       f"Hi {first},\n\nThanks for applying to {rec['job_title']} (ref {reference}). Please complete our 60-minute online "
                       f"assessment on the Northwind test platform. The link expires on {deadline} (UTC).\n\nNorthwind Labs Talent Team"),
        "interview": (f"Interview invitation: {rec['job_title']}",
                      f"Hi {first},\n\nWe'd like to invite you to a 45-minute technical interview for {rec['job_title']} (ref {reference}). "
                      f"Proposed slot: {deadline} (UTC). Reply to confirm.\n\nNorthwind Labs Talent Team"),
        "rejection": (f"Update on your application: {rec['job_title']}",
                      f"Hi {first},\n\nThank you for your interest. Unfortunately we will not be moving forward with your application "
                      f"(ref {reference}) at this time.\n\nNorthwind Labs Talent Team"),
    }
    if kind not in templates:
        return _json(400, {"error": "unknown kind"})
    subject, text = templates[kind]
    message = {"message_id": new_id("msg_"), "reference": reference, "subject": subject, "body": text, "sent_at": clock.iso(),
               "from": "talent@northwind.test", "channel": "test-employer-mailbox"}
    payload = json.dumps(message).encode()
    url = f"{cfg().api_base_url.rstrip('/')}/api/inbound/portal"
    req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json",
                                                                          "X-Portal-Signature": portal_signature(payload.decode())})
    with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310 - our own API
        status = res.status
    return _json(202, {"sent": True, "status": status, "message_id": message["message_id"]})


def _json(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"}, "body": json.dumps(body, default=str)}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def handler(event: dict, context: Any) -> dict:
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/portal").rstrip("/") or "/portal"
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    ensure_seed()
    try:
        if path in ("/portal", "/portal/jobs") and method == "GET":
            return list_page(event)
        if path == "/portal/api/jobs" and method == "GET":
            return _json(200, {"jobs": [job_json(event, j) for j in jobs()], "company": COMPANY, "test_environment": True})
        if path == "/portal/employer" and method == "GET":
            return employer_page()
        if path == "/portal/api/applications/lookup" and method == "GET":
            q = event.get("queryStringParameters") or {}
            job_id, email = q.get("job_id", ""), (q.get("email") or "").lower()
            if not verify_signature(f"{job_id}|{email}", headers.get("x-portal-signature")):
                return _json(403, {"error": "bad signature"})
            rec = store().get(f"PORTAL#APP#{job_id}", f"EMAIL#{email}")
            return _json(200, {"application": {"reference": rec["reference"], "submitted_at": rec["submitted_at"]} if rec else None})
        if path.startswith("/portal/api/admin/") and method == "POST":
            raw = event.get("body") or ""
            if event.get("isBase64Encoded"):
                raw = base64.b64decode(raw).decode()
            if not verify_signature(raw, headers.get("x-portal-signature")):
                return _json(403, {"error": "bad signature"})
            body = json.loads(raw or "{}")
            if path == "/portal/api/admin/jobs":
                return admin_publish(body)
            if path == "/portal/api/admin/reply":
                return admin_reply(event, body)
        m = re.fullmatch(r"/portal/jobs/([a-z0-9-]{3,60})(/apply)?", path)
        if m:
            job = store().get("PORTAL#JOBS", m.group(1))
            if not job or job.get("status") != "open":
                return page("Role not found", "<div class='card'>This role is closed or does not exist.</div>")
            if m.group(2) and method == "POST":
                return submit(event, job)
            if m.group(2):
                return apply_page(job)
            return detail_page(job)
        return page("Not found", "<div class='card'>Page not found.</div>")
    except Exception as exc:  # never leak internals to the page
        log(logger, "portal.error", error=type(exc).__name__, detail=str(exc)[:300])
        return {"statusCode": 500, "headers": {"Content-Type": "text/plain"}, "body": "Something went wrong on the test portal."}


__all__ = ["handler", "Put"]
