"""Shared source polling. One fetch per source per run, regardless of how many users watch it."""

from __future__ import annotations

import re
import time
from typing import Any

from .config import settings as cfg
from .matching import save_job_snapshot
from .sources import greenhouse, portal
from .sources.http import FetchError
from .store import C, Update
from .util import get_logger, log

logger = get_logger("discovery")


def portal_base() -> str:
    return cfg().api_base_url.rstrip("/")


def fetch_source(source: str) -> list[dict]:
    if source == portal.SOURCE:
        return portal.fetch_jobs(portal_base())
    if source.startswith("greenhouse:"):
        return greenhouse.fetch_board(source.split(":", 1)[1])
    raise ValueError(f"unknown source {source}")


def all_sources(extra: list[str] | None = None) -> list[str]:
    boards = [f"greenhouse:{b}" for b in cfg().greenhouse_boards]
    return list(dict.fromkeys([portal.SOURCE, *boards, *(extra or [])]))


def poll(wf, source: str, force: bool = False) -> dict[str, Any]:
    """Fetch a source, persist snapshots, record freshness. Returns new/changed jobs."""
    state_key = (f"SOURCE#{source}", "STATE")
    state = wf.store.get(*state_key) or {}
    if float(state.get("backoff_until", 0)) > wf.clock.now():
        return {"source": source, "skipped": "backoff", "new": [], "changed": []}
    interval = interval_minutes(source)
    if not force and float(state.get("last_success_ts", 0)) > wf.clock.now() - interval * 60 + 20:
        return {"source": source, "skipped": "fresh", "new": [], "changed": []}
    started = time.time()
    try:
        jobs = fetch_source(source)
    except (FetchError, ValueError, KeyError) as exc:
        failures = int(state.get("failures", 0)) + 1
        retry_after = getattr(exc, "retry_after", None)
        delay = int(retry_after) if retry_after and str(retry_after).isdigit() else min(3600, 60 * 2 ** min(failures, 6))
        wf.store.update(Update(*state_key, set={"last_error": str(exc)[:300], "last_error_at": wf.clock.iso(),
                                                "backoff_until": wf.clock.now() + delay, "failures": failures}))
        log(logger, "source.error", source=source, error=str(exc), backoff=delay)
        return {"source": source, "error": str(exc), "new": [], "changed": []}
    new, changed = [], []
    for job in jobs:
        is_new, is_changed = save_job_snapshot(wf, job)
        if is_new:
            new.append(job)
        elif is_changed:
            changed.append(job)
    wf.store.update(Update(*state_key, set={"last_success_at": wf.clock.iso(), "last_success_ts": wf.clock.now(), "failures": 0, "backoff_until": 0,
                                            "job_count": len(jobs), "duration_ms": int((time.time() - started) * 1000)}))
    log(logger, "source.polled", source=source, jobs=len(jobs), new=len(new), changed=len(changed))
    return {"source": source, "new": new, "changed": changed, "count": len(jobs)}


def interval_minutes(source: str) -> int:
    """The test portal is polled every 5 minutes; large live boards every 30 to stay polite and cheap."""
    return 5 if source == portal.SOURCE else 30


def cached_jobs(wf, source: str, limit: int = 300) -> list[dict]:
    return wf.store.query(f"SOURCE#{source}", "", index="gsi1", limit=limit, newest_first=True)


def keyword_filter(jobs: list[dict], keywords: str, prefs: dict) -> list[dict]:
    words = [w for w in re.split(r"[^a-z0-9+#.]+", (keywords or "").lower()) if len(w) > 1 and w not in STOP]
    roles = [r.lower() for r in prefs.get("roles", [])]
    excluded = {c.lower() for c in prefs.get("excluded_companies", [])}
    out = []
    for j in jobs:
        if (j.get("company") or "").lower() in excluded:
            continue
        hay = f"{j.get('title', '')} {j.get('location', '')} {j.get('company', '')} {(j.get('description') or '')[:1500]}".lower()
        title = (j.get("title") or "").lower()
        score = sum(3 if w in title else 1 for w in words if w in hay)
        score += sum(4 for r in roles if r and r in title)
        if not words and not roles:
            score = 1
        if score > 0:
            out.append((score, j))
    out.sort(key=lambda t: (-t[0], t[1].get("first_seen_at") or ""), reverse=False)
    return [j for _, j in out]


STOP = {"find", "me", "jobs", "job", "roles", "role", "for", "in", "the", "and", "or", "a", "an", "with", "show", "search",
        "looking", "want", "please", "any", "new", "openings", "opening", "positions", "position", "at", "to", "of", "i", "am"}


def source_status(wf) -> list[dict]:
    out = []
    for src in all_sources():
        st = wf.store.get(f"SOURCE#{src}", "STATE") or {}
        out.append({"source": src, "last_success_at": st.get("last_success_at"), "last_error": st.get("last_error"),
                    "job_count": st.get("job_count"), "interval_minutes": interval_minutes(src),
                    "environment": "test" if src == portal.SOURCE else "live"})
    return out


__all__ = ["poll", "cached_jobs", "keyword_filter", "all_sources", "source_status", "C"]
