"""Discovery + form reading for the separately hosted Northwind Labs test employer portal."""

from __future__ import annotations

import html
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

from ..util import sha256
from .http import fetch, fetch_json

SOURCE = "northwind-test-portal"


def portal_hosts(base_url: str) -> set[str]:
    host = urllib.parse.urlparse(base_url).hostname
    return {host} if host else set()


def fetch_jobs(base_url: str) -> list[dict]:
    data: Any = fetch_json(f"{base_url.rstrip('/')}/portal/api/jobs", portal_hosts(base_url), timeout=15)
    out = []
    for raw in data.get("jobs", []):
        job = {
            "job_key": f"{SOURCE}:{raw['id']}", "canonical_key": f"{SOURCE}:{raw['requisition_id']}",
            "source": SOURCE, "external_id": raw["id"], "company": raw["company"], "title": raw["title"],
            "location": raw["location"], "work_mode": raw.get("work_mode"), "description": raw["description"],
            "url": raw["url"], "apply": {"kind": "portal", "url": raw["apply_url"]},
            "published_at": raw["published_at"], "updated_at": raw.get("updated_at"),
            "requirements": raw.get("requirements"), "salary_min": raw.get("salary_min"), "salary_max": raw.get("salary_max"),
            "connector": SOURCE, "environment": "test", "test_environment": True, "published_by": raw.get("published_by"),
        }
        job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description", "requirements")})
        out.append(job)
    return out


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, dict] = {}
        self.labels: dict[str, str] = {}
        self._label_for: str | None = None
        self._label_text: list[str] = []
        self._select: str | None = None
        self._option_value: str | None = None
        self._option_text: list[str] = []
        self.form_action: str | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "form" and self.form_action is None:
            self.form_action = a.get("action")
        if tag == "label":
            self._label_for = a.get("for")
            self._label_text = []
        if tag in ("input", "textarea", "select"):
            name = a.get("name")
            itype = a.get("type", "text") if tag == "input" else tag
            if not name or itype in ("hidden", "submit", "button"):
                if tag == "select":
                    self._select = None
                return
            f = self.fields.setdefault(name, {"name": name, "type": itype, "id": a.get("id"), "required": False, "options": []})
            f["required"] = f["required"] or ("required" in a)
            if itype in ("radio", "checkbox") and a.get("value"):
                f["options"].append({"value": a.get("value"), "id": a.get("id")})
            if tag == "select":
                self._select = name
        if tag == "option" and self._select:
            self._option_value = a.get("value", "")
            self._option_text = []

    def handle_data(self, data: str) -> None:
        if self._label_for is not None:
            self._label_text.append(data)
        if self._option_value is not None:
            self._option_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._label_for is not None:
            self.labels[self._label_for] = html.unescape(" ".join("".join(self._label_text).split())).rstrip(" *")
            self._label_for = None
        if tag == "option" and self._select and self._option_value is not None:
            self.fields[self._select]["options"].append({"value": self._option_value, "label": "".join(self._option_text).strip()})
            self._option_value = None
        if tag == "select":
            self._select = None


def parse_form(markup: str) -> dict:
    p = _FormParser()
    p.feed(markup)
    fields = []
    for f in p.fields.values():
        label = p.labels.get(f.get("id") or "", "")
        if not label and f["options"]:
            label = p.labels.get(f["options"][0].get("id") or "", "")
        f["label"] = label or f["name"].replace("_", " ")
        fields.append(f)
    signature = sha256([(f["name"], f["type"], f["required"], f["label"], [o.get("value") for o in f["options"]]) for f in fields])
    return {"fields": fields, "signature": signature, "action": p.form_action}


def read_form(apply_url: str) -> dict:
    parts = urllib.parse.urlparse(apply_url)
    base = f"{parts.scheme}://{parts.netloc}"
    _, data, _ = fetch(apply_url, portal_hosts(base), timeout=15)
    return parse_form(data.decode("utf8", "ignore"))


def lookup_application(base_url: str, job_id: str, email: str, signature: str) -> dict | None:
    q = urllib.parse.urlencode({"job_id": job_id, "email": email})
    data: Any = fetch_json(f"{base_url.rstrip('/')}/portal/api/applications/lookup?{q}", portal_hosts(base_url),
                           headers={"X-Portal-Signature": signature}, timeout=15)
    return data.get("application")


