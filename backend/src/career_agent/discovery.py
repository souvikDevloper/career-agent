"""Shared source polling. One fetch per source per run, regardless of how many users watch it."""

from __future__ import annotations

import re
import time
from typing import Any

from .config import settings as cfg
from .matching import save_job_snapshot
from .sources import amazon, ashby, greenhouse, lever, oraclehcm, portal, workday
from .sources.http import FetchError
from .store import C, Update
from .util import get_logger, log, sha256

logger = get_logger("discovery")


def portal_base() -> str:
    return cfg().api_base_url.rstrip("/")


def fetch_source(source: str) -> list[dict]:
    if source == portal.SOURCE:
        return portal.fetch_jobs(portal_base())
    if source.startswith("greenhouse:"):
        return greenhouse.fetch_board(source.split(":", 1)[1])
    if source.startswith("lever:"):
        return lever.fetch_board(source.split(":", 1)[1])
    if source.startswith("ashby:"):
        return ashby.fetch_board(source.split(":", 1)[1])
    if source.startswith("workday:"):
        return workday.fetch_board(source.split(":", 1)[1])
    if source.startswith("oracle:"):
        return oraclehcm.fetch_board(source.split(":", 1)[1])
    if source.startswith("amazon:"):
        return amazon.fetch_board(source.split(":", 1)[1])
    raise ValueError(f"unknown source {source}")


def all_sources(extra: list[str] | None = None) -> list[str]:
    s = cfg()
    boards = [f"greenhouse:{b}" for b in s.greenhouse_boards]
    boards += [f"lever:{b}" for b in s.lever_boards]
    boards += [f"ashby:{b}" for b in s.ashby_boards]
    boards += [f"workday:{b}" for b in s.workday_boards]
    boards += [f"oracle:{b}" for b in s.oracle_boards]
    boards += [f"amazon:{b}" for b in s.amazon_boards]
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
        # Which configured feed this came from, so search can ask for it by name.
        job["feed"] = source
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


def _dedupe(jobs: list[dict]) -> list[dict]:
    """One row per real opening.

    The test portal can publish the same role repeatedly, and a company on two
    boards appears twice. Three identical cards in one answer reads as a broken
    product regardless of why they are there.
    """
    seen: set = set()
    out = []
    for j in jobs:
        # Deliberately not canonical_key. It comes from the board and boards get
        # it wrong - Stripe returns one placeholder requisition id for every
        # posting - and trusting it collapsed 665 openings into 2. What a person
        # means by "the same job" is the same role, at the same company, in the
        # same place, which is computed here rather than taken on faith.
        key = (
            (j.get("company") or "").lower().strip(),
            (j.get("title") or "").lower().strip(),
            (j.get("location") or "").lower().strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


def hydrate(wf, jobs: list[dict]) -> None:
    """Fill in descriptions that the listing did not carry.

    Workday returns a title and a location in its listing and keeps the
    description one call further in. Fetching that for every posting on every
    poll would be hundreds of requests for text nobody reads, so it happens here
    instead - for the handful that survived filtering and are about to be scored.
    Saved back, so the next search for the same posting costs nothing.
    """
    for job in jobs:
        if job.get("description") or job.get("source") != workday.SOURCE:
            continue
        text = workday.fetch_description(job)
        if not text:
            continue
        job["description"] = text
        job["content_hash"] = sha256({k: job[k] for k in ("title", "location", "description")})
        try:
            save_job_snapshot(wf, job)
        except Exception as exc:  # a cache miss is not worth failing a search over
            log(logger, "source.hydrate_failed", job=job.get("job_key"), error=type(exc).__name__, detail=str(exc)[:120])


_SUFFIXES = ("ings", "ing", "ers", "er", "ies", "es", "s")


def _stem(word: str) -> str:
    """Crude, deliberately.

    A person types "engineering" and the posting says "Engineer"; requiring the
    exact word found nothing for a company with four hundred live openings.
    Trimming a common suffix and matching on the stem as a substring covers
    engineer/engineering/engineers and developer/developers without a
    dependency or a language model.
    """
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _matches(word: str, hay: str) -> bool:
    return word in hay or _stem(word) in hay


def keyword_filter(jobs: list[dict], keywords: str, prefs: dict) -> list[dict]:
    """Every meaningful word in the query has to appear somewhere in the job.

    This was an OR: one matching word was enough to qualify. So "microsoft
    internship" matched anything containing "internship", and a search for a
    company we do not cover came back full of confident results from a company
    the person never asked about. Returning nothing is the honest answer to a
    query nothing matches, and the caller says so.

    Words are still scored for ranking - a hit in the title counts for more than
    one buried in the description - but scoring only orders what already
    qualified.
    """
    words = [w for w in re.split(r"[^a-z0-9+#.]+", (keywords or "").lower()) if len(w) > 1 and w not in STOP]
    roles = [r.lower() for r in prefs.get("roles", [])]
    excluded = {c.lower() for c in prefs.get("excluded_companies", [])}
    out = []
    for j in _dedupe(jobs):
        if (j.get("company") or "").lower() in excluded:
            continue
        title = (j.get("title") or "").lower()
        hay = f"{title} {j.get('location', '')} {j.get('company', '')} {(j.get('description') or '')[:1500]}".lower()
        if words and not all(_matches(w, hay) for w in words):
            continue
        score = sum(3 if _matches(w, title) else 1 for w in words)
        score += sum(4 for r in roles if r and r in title)
        if not words and not roles:
            score = 1
        if score > 0:
            out.append((score, j))
    out.sort(key=lambda t: (-t[0], t[1].get("first_seen_at") or ""))
    return [j for _, j in out]


STOP = {"find", "me", "jobs", "job", "roles", "role", "for", "in", "the", "and", "or", "a", "an", "with", "show", "search",
        "looking", "want", "please", "any", "new", "openings", "opening", "positions", "position", "at", "to", "of", "i", "am",
        "my", "that", "fit", "fits", "relevant", "some", "good", "best", "get", "give", "resume", "match", "matching", "is",
        "are", "can", "you", "it", "on", "near", "around"}


def source_status(wf) -> list[dict]:
    out = []
    for src in all_sources():
        st = wf.store.get(f"SOURCE#{src}", "STATE") or {}
        out.append({"source": src, "last_success_at": st.get("last_success_at"), "last_error": st.get("last_error"),
                    "job_count": st.get("job_count"), "interval_minutes": interval_minutes(src),
                    "environment": "test" if src == portal.SOURCE else "live"})
    return out


__all__ = ["poll", "cached_jobs", "keyword_filter", "all_sources", "source_status", "C"]
