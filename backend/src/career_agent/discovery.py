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
    first = [portal.SOURCE] if s.enable_test_employer else []
    return list(dict.fromkeys([*first, *boards, *(extra or [])]))



def live_search(wf, *, company: str, role: str = "", limit: int = 100) -> list[dict]:
    """Ask the employer's own search, for boards too large to mirror.

    Polling keeps a cache so the whole corpus can be browsed. But Amazon India
    alone publishes 2,322 openings and paging all of them takes 98 seconds, so
    the poller kept the 400 most recent - and someone searching for "SDE 1 in
    Bengaluru" was told none existed while five were live, purely because they
    were not among the newest 400.

    Naming an employer is a question that employer can answer directly, and it
    comes back complete in about a second. Results are snapshotted on the way
    through so an application can be prepared from one immediately.
    """
    wanted = (company or "").strip().lower()
    if not wanted:
        return []
    s = cfg()
    asks: list[tuple[str, Any]] = []
    if _names_match(wanted, "amazon"):
        for spec in s.amazon_boards:
            country, preset = amazon.parse_spec(spec)
            asks.append((f"amazon:{spec}", lambda c=country, p=preset: amazon.search(c, role or p or "", limit=limit)))
    for spec in s.workday_boards:
        tenant = spec.split(":", 1)[0].lower()
        if _names_match(wanted, tenant):
            asks.append((f"workday:{spec}", lambda sp=spec: workday.search(sp, role)))

    out: list[dict] = []
    for feed, ask in asks:
        try:
            found = ask()
        except (FetchError, ValueError, KeyError) as exc:
            log(logger, "warning", "live_search_failed", feed=feed, error=str(exc)[:200])
            continue
        for job in found:
            job["feed"] = feed
            try:
                save_job_snapshot(wf, job)
            except Exception as exc:  # a job we cannot store is still worth answering with
                log(logger, "warning", "live_snapshot_failed", job=job.get("job_key"), error=str(exc)[:160])
        log(logger, "info", "live_search", feed=feed, role=role, found=len(found))
        out.extend(found)
    return out


def _names_match(wanted: str, name: str) -> bool:
    """Whether a typed employer name refers to this board.

    Containment only once both names are long enough for it not to be a
    coincidence: "hp" and the Workday tenant "hpe" are different companies.
    """
    if wanted == name:
        return True
    return len(wanted) >= 4 and len(name) >= 4 and (wanted in name or name in wanted)


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


# Boards spell one country several ways: "IND", "India", "Remote - India".
# A place is an equivalence class, not a one-way lookup.
#
# "Bangalore" and "Bengaluru" are one city spelled two ways, so a search for
# either has to match a posting written the other way; the first version of this
# table only mapped country -> city, so "bangalore" matched nothing at all while
# "india" worked, and Amazon's 204 Bengaluru openings were invisible to anyone
# who typed the spelling they actually use.
_SAME_PLACE = (
    ("bangalore", "bengaluru"),
    ("gurgaon", "gurugram"),
    ("bombay", "mumbai"),
    ("madras", "chennai"),
    ("calcutta", "kolkata"),
    ("poona", "pune"),
    ("trivandrum", "thiruvananthapuram"),
    ("nyc", "new york"),
    ("sf", "san francisco"),
    ("bengaluru", "blr"),
)

# Containment is deliberately one-way: a region matches its cities, because a
# person asking for India means any of them, but a city does not match the bare
# region - someone who asks for Bengaluru has not asked for Delhi.
_REGIONS = {
    "india": ("ind", "bengaluru", "hyderabad", "pune", "chennai", "mumbai", "delhi",
              "noida", "gurgaon", "kolkata", "ahmedabad", "jaipur", "trivandrum", "coimbatore"),
    "usa": ("us", "united states", "america"),
    "uk": ("united kingdom", "england", "london"),
    "emea": ("europe", "united kingdom", "ireland", "germany", "france", "netherlands", "spain", "poland"),
    "apac": ("singapore", "japan", "australia", "korea", "taiwan", "china", "hong kong"),
}


def _build_place_aliases() -> dict[str, tuple[str, ...]]:
    """Every spelling that should satisfy a search for one place."""
    same: dict[str, set] = {}
    for group in _SAME_PLACE:
        for word in group:
            same.setdefault(word, set()).update(group)
    out = {word: set(forms) for word, forms in same.items()}
    for region, members in _REGIONS.items():
        forms = {region}
        for member in members:
            forms.update(same.get(member, {member}))
        out.setdefault(region, set()).update(forms)
    return {word: tuple(sorted(forms)) for word, forms in out.items()}


_PLACE_ALIASES = _build_place_aliases()


def _field_tokens(jobs: list[dict], field: str) -> set:
    """The distinct words that appear in one field across the corpus.

    Used to tell "is this word naming a company/place, or describing a job?" -
    which is the difference between a filter and a search term.
    """
    out: set = set()
    for job in jobs:
        for token in re.split(r"[^a-z0-9]+", (job.get(field) or "").lower()):
            if len(token) > 2:
                out.add(token)
    for name, forms in _PLACE_ALIASES.items():
        if any(all(w in out for w in form.split()) for form in forms):
            out.add(name)
    return out


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

    A person types "engineering" and the posting says "Engineer". Trimming a
    common suffix and matching the stem as a substring covers the forms people
    use without a dependency or a model.
    """
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


# What people type versus what a posting is titled. "amazon sde" found nothing
# because every Amazon title says "Software Dev Engineer".
ALIASES = {
    "sde": ("software development engineer", "software dev engineer", "software engineer"),
    "swe": ("software engineer", "software development engineer"),
    "sre": ("site reliability engineer",),
    "ml": ("machine learning",),
    "ai": ("artificial intelligence", "machine learning"),
    "ds": ("data scientist", "data science"),
    "pm": ("product manager",),
    "qa": ("quality assurance", "test engineer"),
    "devops": ("devops", "platform engineer", "infrastructure"),
    "fullstack": ("full stack", "full-stack"),
    "frontend": ("frontend", "front end", "front-end"),
    "backend": ("backend", "back end", "back-end"),
    "newgrad": ("new grad", "graduate", "entry level"),
    "fresher": ("graduate", "entry level", "intern"),
    # Boards title the same thing both ways; a person types one of them.
    "internship": ("intern",),
    "interns": ("intern",),
}


# A word, plus the endings English puts on it. Substring matching made "intern"
# match "Internal Audit" and "Internal Systems", which is how a search for an
# internship returned a Senior Manager role.
_ENDINGS = r"(?:s|es|ed|ing|ings|er|ers|ship|ships)?\b"


def _matches(word: str, hay: str) -> bool:
    for form in (word, _stem(word)):
        if re.search(r"\b" + re.escape(form) + _ENDINGS, hay):
            return True
    # The closing boundary matters here too: without it the alias "intern"
    # matched "Internal", which is the bug this function was fixing.
    return any(re.search(r"\b" + re.escape(alias) + _ENDINGS, hay) for alias in ALIASES.get(word, ()))


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9+#.]+", (text or "").lower()) if len(w) > 1 and w not in STOP]


_LEVELS = {"1": 1, "i": 1, "one": 1, "2": 2, "ii": 2, "two": 2,
           "3": 3, "iii": 3, "three": 3, "4": 4, "iv": 4, "four": 4}
_LEVEL_RE = re.compile(r"\b(iv|iii|ii|[1-4])\b")


def _wanted_level(role: str) -> int | None:
    """"SDE 2" names a level, and someone asking for one does not want the other.

    A bare numeral with no role word in front of it is not a level, so "2 jobs"
    does not silently become a seniority filter.
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", (role or "").lower()) if t]
    for i, token in enumerate(tokens):
        hit = re.fullmatch(r"(?:sde|swe|l)([1-4])", token)
        if hit:
            return int(hit.group(1))
        if token in _LEVELS and i > 0:
            return _LEVELS[token]
    return None


def _title_level(title: str) -> int:
    """Amazon writes SDE I as "Software Development Engineer" with no numeral."""
    hit = _LEVEL_RE.search((title or "").lower())
    return _LEVELS.get(hit.group(1), 1) if hit else 1


def _place_matches(wanted: str, location: str) -> bool:
    """One place, spelled the way each board spells it.

    Amazon writes "Bengaluru, Karnataka, IND", Stripe writes "Bengaluru, India",
    Twilio writes "Remote - India". A person types one word for all three.
    """
    place = (location or "").lower()
    for word in _words(wanted):
        # Whole words only. As a substring, "ind" sits inside "Windsor", so a
        # search for India used to return jobs in Windsor, Ontario.
        forms = _PLACE_ALIASES.get(word, (word,))
        if not any(re.search(r"\b" + re.escape(form) + r"\b", place) for form in forms):
            return False
    return True


def filter_jobs(jobs: list[dict], prefs: dict, *, role: str = "", company: str = "", location: str = "",
                work_mode: str = "", employment_type: str = "") -> list[dict]:
    """Structured filters, applied exactly. No guessing what a word meant.

    This replaced a single free-text string that the backend tried to interpret
    with heuristics, and got wrong three times in a row: a search for NVIDIA
    returned Stripe roles that listed "NVIDIA NeMo" in their requirements, and a
    search for India returned a role in Seoul whose description mentioned India.
    Both were true statements about the posting and useless as answers.

    The caller knows which word is a company and which is a place - a language
    model is good at exactly that - so it says so, and each filter is applied to
    the field it names. Only `role` is a text search, and only across the parts
    of a posting that describe the work.
    """
    role_words = _words(role)
    company_words = _words(company)
    excluded = {c.lower() for c in prefs.get("excluded_companies", [])}
    preferred_roles = [r.lower() for r in prefs.get("roles", [])]
    level = _wanted_level(role)
    mode = (work_mode or "").strip().lower()
    kind = (employment_type or "").strip().lower()

    out = []
    for job in _dedupe(jobs):
        employer = (job.get("company") or "").lower()
        if employer in excluded:
            continue
        # Compared without punctuation, because a board writes "Match Group" and a
        # person types "matchgroup". Every word must be there: naming two
        # employers matches nothing, which is the truth rather than a guess at
        # which one was meant.
        squashed = re.sub(r"[^a-z0-9]", "", employer)
        if company_words and not all(re.sub(r"[^a-z0-9]", "", w) in squashed for w in company_words):
            continue
        if location and not _place_matches(location, job.get("location") or ""):
            continue
        if mode and (job.get("work_mode") or "").lower() != mode:
            continue
        if kind and kind not in (job.get("employment_type") or "").lower():
            continue

        title = (job.get("title") or "").lower()
        if level is not None and _title_level(title) != level:
            continue
        hay = f"{title} {(job.get('description') or '')[:1500]} {' '.join(job.get('departments') or [])}".lower()
        if role_words and not all(_matches(w, hay) for w in role_words):
            continue

        score = sum(3 if _matches(w, title) else 1 for w in role_words)
        score += sum(4 for r in preferred_roles if r and r in title)
        score += 2 * bool(company_words) + 2 * bool(location)
        out.append((score or 1, job))

    out.sort(key=lambda t: (-t[0], t[1].get("first_seen_at") or ""))
    return [j for _, j in out]


def parse_query(jobs: list[dict], keywords: str) -> dict:
    """Free text to structured filters, for callers that only have a string.

    The agent passes filters directly and never comes through here. This exists
    for the REST search endpoint and for a person typing into a box, and it
    decides what a word names by looking at what is actually in the corpus.
    """
    words = _words(keywords)
    companies = _field_tokens(jobs, "company")
    places = _field_tokens(jobs, "location") - companies
    return {
        # Every company word is kept, not just the first. Dropping one silently
        # answers a different question than the one that was asked.
        "company": " ".join(w for w in words if w in companies),
        "location": " ".join(w for w in words if w in places),
        "role": " ".join(w for w in words if w not in companies and w not in places),
    }


def keyword_filter(jobs: list[dict], keywords: str, prefs: dict) -> list[dict]:
    """Back-compatible free-text search, over the same one implementation."""
    return filter_jobs(jobs, prefs, **parse_query(jobs, keywords))


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


__all__ = ["poll", "cached_jobs", "keyword_filter", "live_search", "all_sources", "source_status", "C"]
