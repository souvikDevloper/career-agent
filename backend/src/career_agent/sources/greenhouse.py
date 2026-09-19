"""Greenhouse public job board discovery (no key required for GET endpoints)."""

from __future__ import annotations

import html
import re
from typing import Any

from ..util import sha256
from .http import fetch_json

HOSTS = {"boards-api.greenhouse.io"}
SOURCE = "greenhouse-public"


def html_to_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _requisition(raw: dict) -> str:
    """Greenhouse's requisition_id is free text and boards abuse it.

    Stripe returns the literal sentence "See Opening ID" for all 665 of its
    postings, which collapsed the whole board to a single canonical key. Only
    accept something that looks like an identifier; otherwise fall back to the
    posting id, which is always unique.
    """
    value = str(raw.get("requisition_id") or "").strip()
    return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{1,48}", value) else str(raw["id"])


GREENHOUSE_HOSTED = "job-boards.greenhouse.io"


def _apply_target(board: str, raw: dict) -> dict:
    absolute = raw.get("absolute_url") or ""
    if GREENHOUSE_HOSTED in absolute:
        return {"kind": "hosted_form", "url": f"https://{GREENHOUSE_HOSTED}/{board}/jobs/{raw['id']}"}
    return {"kind": "external", "url": absolute or None}


def normalize(board: str, raw: dict) -> dict:
    description = html_to_text(raw.get("content", ""))
    loc = (raw.get("location") or {}).get("name") or ""
    job = {
        "job_key": f"greenhouse:{board}:{raw['id']}",
        "canonical_key": f"greenhouse:{board}:{_requisition(raw)}",
        "source": SOURCE,
        "board": board,
        "external_id": str(raw["id"]),
        "company": board.replace("-", " ").title(),
        "title": raw.get("title", "").strip(),
        "location": loc,
        "work_mode": "remote" if "remote" in loc.lower() else None,
        "description": description[:12000],
        "url": raw.get("absolute_url"),
        # Some employers host the application on Greenhouse; others embed it in
        # their own careers site, where the form sits behind their bot protection
        # and is not ours to drive. The board itself says which, so the answer is
        # read off the posting rather than kept in a list we would have to curate.
        "apply": _apply_target(board, raw),
        "published_at": raw.get("first_published") or raw.get("updated_at"),
        "updated_at": raw.get("updated_at"),
        "departments": [d.get("name") for d in raw.get("departments") or []],
        "requirements": None,  # extracted lazily by the model only for candidate matches
        "connector": SOURCE,
        "environment": "live",
    }
    job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
    return job


def fetch_board(board: str) -> list[dict]:
    if not re.fullmatch(r"[a-z0-9-]{2,60}", board):
        raise ValueError("invalid board token")
    data: Any = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true", HOSTS, timeout=20)
    return [normalize(board, j) for j in data.get("jobs", [])]


# Greenhouse publishes each job's real application form - every field name, its
# type, and whether it is required - on the same unauthenticated endpoint that
# serves the posting. That is the difference between guessing at a form and
# answering the one the employer will actually receive: a packet can be checked
# for completeness before a browser is ever opened.
_TYPES = {
    "input_text": "text",
    "textarea": "textarea",
    "input_file": "file",
    "multi_value_single_select": "select",
    "multi_value_multi_select": "select",
}


def parse_questions(questions: list[dict]) -> dict:
    """Normalise Greenhouse's question list into the shape the packet builder reads."""
    fields: list[dict] = []
    for question in questions or []:
        label = (question.get("label") or "").strip()
        required = bool(question.get("required"))
        for field in question.get("fields") or []:
            name = field.get("name")
            if not name:
                continue
            options = [{"label": str(v.get("label", "")), "value": str(v.get("value", ""))}
                       for v in (field.get("values") or [])]
            fields.append({
                "name": name,
                "type": _TYPES.get(field.get("type", ""), "text"),
                "required": required,
                "label": label or name.replace("_", " "),
                "options": options,
            })
    signature = sha256([(f["name"], f["type"], f["required"], f["label"],
                         [o["value"] for o in f["options"]]) for f in fields])
    return {"fields": fields, "signature": signature, "action": None}


def read_form(board: str, job_id: str) -> dict:
    data: Any = fetch_json(
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true", HOSTS, timeout=20)
    if not isinstance(data, dict):
        raise ValueError("greenhouse returned no job")
    form = parse_questions(data.get("questions") or [])
    if not form["fields"]:
        raise ValueError("greenhouse returned no application questions")
    return form
