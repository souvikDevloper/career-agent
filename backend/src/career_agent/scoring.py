"""Deterministic eligibility filters and the versioned 0-100 fit rubric.

The language model only *extracts evidence* (which resume passage supports which
requirement). Arithmetic, thresholds and eligibility live here so they are
reproducible, testable and cannot be talked around by prompt content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any

RUBRIC_VERSION = "fit-rubric/2.0"
WEIGHTS = {"required_skills": 40, "experience": 30, "responsibilities": 20, "preferences": 10}

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"


@dataclass
class FilterResult:
    check: str
    status: str
    detail: str
    mandatory: bool = True

    def to_dict(self) -> dict:
        return {"check": self.check, "status": self.status, "detail": self.detail, "mandatory": self.mandatory}


@dataclass
class Evidence:
    """What the extractor found. Scores are 0..1; quotes must come from the resume."""

    skills: list[dict] = field(default_factory=list)  # {skill, required: bool, evidence: str|None}
    experience: float = 0.0
    experience_evidence: list[str] = field(default_factory=list)
    responsibilities: float = 0.0
    responsibilities_evidence: list[str] = field(default_factory=list)
    extractor: str = "model"
    confidence: float = 0.0


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", (s or "").lower()).strip()


def work_mode_of(job: dict) -> str:
    mode = (job.get("work_mode") or "").lower()
    if mode in {"remote", "hybrid", "onsite"}:
        return mode
    text = _norm(f"{job.get('location', '')} {job.get('title', '')}")
    if "remote" in text:
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    return "unknown"


def hard_filters(job: dict, prefs: dict, facts: dict) -> list[FilterResult]:
    out: list[FilterResult] = []

    roles = [_norm(r) for r in prefs.get("roles", []) if r]
    if roles:
        title = _norm(job.get("title"))
        hit = any(all(tok in title for tok in r.split()) for r in roles)
        # A saved role is a preference, not an eligibility rule. A user who
        # explicitly searches for a different role must still be allowed to
        # inspect and prepare it.
        out.append(FilterResult("role", PASS if hit else FAIL,
                                f"title '{job.get('title')}' vs {prefs.get('roles')}", mandatory=False))

    excluded = {_norm(c) for c in prefs.get("excluded_companies", []) if c}
    if excluded:
        comp = _norm(job.get("company"))
        out.append(FilterResult("company_exclusion", FAIL if comp in excluded else PASS, job.get("company") or ""))

    modes = [m.lower() for m in prefs.get("work_modes", []) if m]
    if modes:
        mode = work_mode_of(job)
        status = UNKNOWN if mode == "unknown" else (PASS if mode in modes else FAIL)
        out.append(FilterResult("work_mode", status, f"job is {mode}; wants {modes}", mandatory=False))

    locs = [_norm(loc) for loc in prefs.get("locations", []) if loc]
    if locs:
        jl = _norm(job.get("location"))
        mode = work_mode_of(job)
        if not jl:
            status = UNKNOWN
        elif any(loc in jl for loc in locs) or ("remote" in locs and mode == "remote"):
            status = PASS
        else:
            status = FAIL
        # Saved locations steer ranking; they do not make an otherwise eligible
        # posting impossible to apply to.
        out.append(FilterResult("location", status,
                                f"'{job.get('location')}' vs {prefs.get('locations')}", mandatory=False))

    req = job.get("requirements") or {}
    min_years = req.get("min_years")
    if min_years is not None:
        have = facts.get("years_experience")
        source = "stated on your profile"
        if have is None:
            # The dates are already on the resume; not stating a total is not the
            # same as having nothing to state.
            have = derived_years(facts)
            source = "from the dates on your roles"
        if have is None:
            out.append(FilterResult("experience_years", UNKNOWN,
                                    f"job needs {min_years}y; no dated roles on the resume to work it out from"))
        else:
            out.append(FilterResult("experience_years", PASS if have >= min_years else FAIL,
                                    f"needs {min_years}y, have {have}y ({source})"))

    grad_years = req.get("graduation_years") or []
    if grad_years:
        years = [e.get("graduation_year") for e in facts.get("education", []) if e.get("graduation_year")]
        if not years:
            out.append(FilterResult("graduation_eligibility", UNKNOWN, f"job accepts {grad_years}; graduation year unknown"))
        else:
            ok = any(int(y) in [int(g) for g in grad_years] for y in years)
            out.append(FilterResult("graduation_eligibility", PASS if ok else FAIL, f"accepts {grad_years}, have {years}"))

    min_salary = prefs.get("min_salary")
    if min_salary:
        top = job.get("salary_max")
        if top is None:
            out.append(FilterResult("salary", UNKNOWN, "salary not published", mandatory=False))
        else:
            out.append(FilterResult("salary", PASS if top >= min_salary else FAIL, f"max {top} vs min {min_salary}"))

    if req.get("work_authorization_required"):
        auth = (facts.get("work_authorization") or {})
        if not auth.get("verified"):
            out.append(FilterResult("work_authorization", UNKNOWN, "employer requires work authorization; ask the user"))
        else:
            value = _norm(str(auth.get("value") or ""))
            negative = value in {"no", "false", "not authorized", "not authorised"} or value.startswith("no ")
            positive = value in {"yes", "true", "authorized", "authorised"} or any(
                phrase in value for phrase in ("citizen", "permanent resident", "work permit", "authorized to work", "authorised to work")
            )
            if negative:
                out.append(FilterResult("work_authorization", FAIL, f"user-confirmed: {auth.get('value')}"))
            elif positive:
                out.append(FilterResult("work_authorization", PASS, f"user-confirmed: {auth.get('value')}"))
            else:
                out.append(FilterResult("work_authorization", UNKNOWN,
                                        f"work authorization answer needs review: {auth.get('value')}"))
    return out


def preference_score(job: dict, prefs: dict, filters: list[FilterResult] | None = None) -> float:
    """Preference contribution, with no-preference meaning neutral rather than perfect.

    The previous rubric silently awarded the full 10/10 whenever the user had
    configured no preference at all. At the same time, saved roles/locations
    were hard blockers. Both behaviours inverted what a preference should mean.
    """
    checks: list[float] = []
    for f in filters or []:
        if not f.mandatory and f.check in {"role", "location", "work_mode", "salary"}:
            checks.append(1.0 if f.status == PASS else 0.5 if f.status == UNKNOWN else 0.0)
    liked = [_norm(c) for c in prefs.get("preferred_companies", []) if c]
    if liked:
        checks.append(1.0 if _norm(job.get("company")) in liked else 0.3)
    return sum(checks) / len(checks) if checks else 0.5


def _evidence_backed(value: Any, quotes: list[str]) -> float:
    """Do not grant near-full subjective credit from one vague resume passage."""
    raw = _clamp(value)
    unique = len({re.sub(r"\s+", " ", q.strip().lower()) for q in quotes if q and q.strip()})
    cap = (0.2, 0.6, 0.8, 1.0)[min(unique, 3)]
    return min(raw, cap)


@dataclass
class MatchResult:
    score: int
    components: dict
    filters: list[FilterResult]
    evidence: Evidence
    unknowns: list[str]
    blocked: bool
    rubric_version: str = RUBRIC_VERSION

    @property
    def auto_eligible(self) -> bool:
        return not self.blocked and not self.unknowns

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "components": self.components,
            "filters": [f.to_dict() for f in self.filters],
            "skills": self.evidence.skills,
            "experience_evidence": self.evidence.experience_evidence,
            "responsibilities_evidence": self.evidence.responsibilities_evidence,
            "extractor": self.evidence.extractor,
            "confidence": self.evidence.confidence,
            "unknowns": self.unknowns,
            "blocked": self.blocked,
            "auto_eligible": self.auto_eligible,
            "rubric_version": self.rubric_version,
        }


def _clamp(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def score_match(job: dict, prefs: dict, facts: dict, evidence: Evidence) -> MatchResult:
    filters = hard_filters(job, prefs, facts)
    required = [s for s in evidence.skills if s.get("required", True)]
    preferred = [s for s in evidence.skills if not s.get("required", True)]
    if required:
        required_ratio = sum(1 for s in required if s.get("evidence")) / len(required)
        if preferred:
            preferred_ratio = sum(1 for s in preferred if s.get("evidence")) / len(preferred)
            # Must-haves dominate; nice-to-haves can move at most four points.
            skills_ratio = 0.9 * required_ratio + 0.1 * preferred_ratio
        else:
            skills_ratio = required_ratio
    else:
        skills_ratio = 0.5  # no explicit must-haves: neutral, not a free pass
    components = {
        "required_skills": round(WEIGHTS["required_skills"] * skills_ratio, 1),
        "experience": round(WEIGHTS["experience"] * _evidence_backed(evidence.experience, evidence.experience_evidence), 1),
        "responsibilities": round(WEIGHTS["responsibilities"] * _evidence_backed(
            evidence.responsibilities, evidence.responsibilities_evidence), 1),
        "preferences": round(WEIGHTS["preferences"] * preference_score(job, prefs, filters), 1),
    }
    score = int(round(sum(components.values())))
    blocked = any(f.status == FAIL and f.mandatory for f in filters)
    unknowns = [f.detail for f in filters if f.status == UNKNOWN and f.mandatory]
    return MatchResult(score=max(0, min(100, score)), components=components, filters=filters,
                       evidence=evidence, unknowns=unknowns, blocked=blocked)


# ---------------------------------------------------------------------------
# Heuristic extractor: used in tests and as a clearly-labelled fallback when the
# model is unavailable or the budget is exhausted. It only credits skills whose
# name literally appears in the resume text and quotes that passage.
# ---------------------------------------------------------------------------


def _passage(text: str, needle: str, width: int = 70) -> str | None:
    m = re.search(r"(?<![a-z0-9])" + re.escape(needle.lower()) + r"(?![a-z0-9])", text.lower())
    if not m:
        return None
    start, end = max(0, m.start() - width), min(len(text), m.end() + width)
    return text[start:end].strip()


def heuristic_evidence(job: dict, resume_text: str) -> Evidence:
    req = job.get("requirements") or {}
    skills = []
    for name in req.get("required_skills", []):
        skills.append({"skill": name, "required": True, "evidence": _passage(resume_text, name)})
    for name in req.get("preferred_skills", []):
        skills.append({"skill": name, "required": False, "evidence": _passage(resume_text, name)})
    resp_hits = []
    for r in req.get("responsibilities", []):
        words = [w for w in _norm(r).split() if len(w) > 4][:4]
        hits = [w for w in words if w in resume_text.lower()]
        if words and len(hits) >= max(1, len(words) // 2):
            resp_hits.append(r)
    resp = len(resp_hits) / len(req.get("responsibilities") or [1])
    title_words = [w for w in _norm(job.get("title")).split() if len(w) > 3]
    exp_hits = [w for w in title_words if w in resume_text.lower()]
    exp = len(exp_hits) / len(title_words) if title_words else 0.3
    return Evidence(
        skills=skills,
        experience=min(1.0, exp),
        experience_evidence=[p for w in exp_hits if (p := _passage(resume_text, w))][:3],
        responsibilities=resp,
        responsibilities_evidence=resp_hits[:3],
        extractor="heuristic",
        confidence=0.4,
    )


def verify_quotes(evidence: Evidence, resume_text: str) -> Evidence:
    """Drop any model-provided quote that does not appear in the resume (anti-hallucination)."""
    hay = re.sub(r"\s+", " ", resume_text.lower())

    def ok(q: str | None) -> bool:
        if not q:
            return False
        q2 = re.sub(r"\s+", " ", q.lower()).strip(" .\"'")
        return len(q2) >= 3 and q2[:120] in hay

    for s in evidence.skills:
        if s.get("evidence") and not ok(s["evidence"]):
            s["evidence"] = None
            s["dropped_unverified_quote"] = True
    evidence.experience_evidence = [q for q in evidence.experience_evidence if ok(q)]
    evidence.responsibilities_evidence = [q for q in evidence.responsibilities_evidence if ok(q)]
    if not evidence.experience_evidence:
        evidence.experience = min(evidence.experience, 0.2)
    if not evidence.responsibilities_evidence:
        evidence.responsibilities = min(evidence.responsibilities, 0.2)
    return evidence


# ---------------------------------------------------------------------------
# Experience the resume already proves
# ---------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_ONGOING = ("present", "current", "now", "ongoing", "till date", "to date")


def _month_index(text: str | None, *, default_month: int) -> int | None:
    """Months since year zero, from the shapes resumes actually write dates in."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if any(word in t for word in _ONGOING):
        today = _date.today()
        return today.year * 12 + today.month
    iso = re.match(r"(\d{4})[-/](\d{1,2})", t)
    if iso:
        return int(iso.group(1)) * 12 + min(12, max(1, int(iso.group(2))))
    slashed = re.match(r"(\d{1,2})[-/](\d{4})", t)
    if slashed:
        return int(slashed.group(2)) * 12 + min(12, max(1, int(slashed.group(1))))
    named = re.search(r"([a-z]{3,9})\.?\s+(\d{4})", t)
    if named and named.group(1)[:3] in _MONTHS:
        return int(named.group(2)) * 12 + _MONTHS[named.group(1)[:3]]
    year = re.search(r"(?:19|20)\d{2}", t)
    if year:
        return int(year.group(0)) * 12 + default_month
    return None


def derived_years(facts: dict) -> float | None:
    """Total experience, worked out from the roles the resume already lists.

    A profile with no stated total is not a person with no experience, but the
    scorer treated it as one: every posting with a minimum-years requirement came
    back "profile has no verified total", which reads as "it does not know my
    experience" while the dates sit in the roles it had already extracted.

    Overlapping roles count once. Two jobs held in the same year is one year of
    experience, not two, and a resume listing a long-running open source role
    alongside an internship should not be credited twice for the same months.
    """
    spans: list[tuple[int, int]] = []
    for role in facts.get("experience") or []:
        # A bare "2021 - 2022" is read as mid-year to mid-year. Stretching it to
        # January-to-December would credit two years for what is usually one, and
        # overstating someone's experience on an application is the one direction
        # this must not be wrong in.
        start = _month_index(role.get("start"), default_month=6)
        if start is None:
            continue
        end = _month_index(role.get("end") or "present", default_month=6)
        spans.append((start, max(start, end if end is not None else start)))
    if not spans:
        return None
    spans.sort()
    total, cur_start, cur_end = 0, *spans[0]
    for start, end in spans[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    total += cur_end - cur_start
    return round(total / 12, 1)
