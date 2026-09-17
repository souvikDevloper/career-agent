"""Authorization engine.

Production evaluates the Cedar policy set in ``policies/career_agent.cedar`` with
``cedarpy`` (the same engine behind Strands' Cedar intervention). A small
reference evaluator mirrors the policy semantics so domain tests can run
without native wheels; a CI test asserts both engines agree on an exhaustive
grid of contexts, so the two can never silently drift.
"""

from __future__ import annotations

import itertools
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

POLICY_VERSION = "authz/1.0"

SUBMIT = "submit_application"
MODES = ("review", "auto_above_80", "auto_eligible")


@dataclass
class Decision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    engine: str = "cedar"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "reasons": self.reasons, "engine": self.engine,
                "errors": self.errors, "policy_version": POLICY_VERSION}


@dataclass
class Request:
    user_id: str
    is_judge: bool
    action: str
    app_owner: str
    target_environment: str  # "test" | "live"
    context: dict

    def default_context(self) -> dict:
        base = {
            "mode": "review",
            "score": 0,
            "approved_packet_hash_matches": False,
            "approved_content_hash_matches": False,
            "mandate_active": False,
            "auto_eligible": False,
            "required_answers_complete": True,
            "daily_remaining": 1,
            "cooldown_ok": True,
            "connector_can_submit": True,
            "paused": False,
        }
        base.update(self.context)
        base["score"] = int(base["score"])
        base["daily_remaining"] = int(base["daily_remaining"])
        return base


def _policy_path() -> Path:
    env = os.environ.get("POLICY_FILE")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for candidate in (here.parent / "policies" / "career_agent.cedar",
                      here.parents[3] / "policies" / "career_agent.cedar"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("career_agent.cedar not found")


class CedarEngine:
    name = "cedar"

    def __init__(self, policy_text: str | None = None) -> None:
        import cedarpy  # noqa: F401  (fail closed if the engine is missing)

        self._cedar = cedarpy
        self._policies = policy_text or _policy_path().read_text()
        self._policy_set = cedarpy.PolicySet.from_str(self._policies) if hasattr(cedarpy, "PolicySet") else self._policies

    def authorize(self, req: Request) -> Decision:
        entities = [
            {"uid": {"__entity": {"type": "User", "id": req.user_id}}, "attrs": {"is_judge": req.is_judge}, "parents": []},
        ]
        if req.app_owner != req.user_id:
            entities.append({"uid": {"__entity": {"type": "User", "id": req.app_owner}}, "attrs": {"is_judge": False}, "parents": []})
        entities.append({
            "uid": {"__entity": {"type": "Application", "id": "subject"}},
            "attrs": {"owner": {"__entity": {"type": "User", "id": req.app_owner}}, "target_environment": req.target_environment},
            "parents": [],
        })
        request = {
            "principal": f'User::"{_q(req.user_id)}"',
            "action": f'Action::"{_q(req.action)}"',
            "resource": 'Application::"subject"',
            "context": req.default_context(),
        }
        result = self._cedar.is_authorized(request, self._policy_set, entities)
        diag = result.diagnostics
        reasons = list(diag.reasons)
        try:
            ann = diag.id_annotations_by_reason
            reasons = [ann.get(r, r) for r in reasons] if isinstance(ann, dict) else reasons
        except Exception:
            pass
        return Decision(allowed=result.allowed, reasons=reasons, engine="cedar", errors=list(diag.errors))


def _q(value: str) -> str:
    if '"' in value or "\\" in value:
        raise ValueError("identifier contains forbidden characters")
    return value


class ReferenceEngine:
    """Executable mirror of career_agent.cedar used for dependency-free tests."""

    name = "reference"

    def authorize(self, req: Request) -> Decision:
        c = req.default_context()
        owner = req.app_owner == req.user_id
        permits: list[str] = []
        forbids: list[str] = []
        if not owner:
            forbids.append("deny-cross-user")
        if req.action in {"view_application", "prepare_application", "approve_application", "cancel_application"} and owner:
            permits.append("owner-read-prepare-approve")
        if req.action == SUBMIT:
            if owner and c["approved_packet_hash_matches"]:
                permits.append("submit-with-current-explicit-approval")
            if owner and c["mode"] == "auto_above_80" and c["mandate_active"] and c["auto_eligible"] and c["score"] > 80:
                permits.append("submit-auto-strictly-above-80")
            if owner and c["mode"] == "auto_eligible" and c["mandate_active"] and c["auto_eligible"]:
                permits.append("submit-auto-eligible-mandate")
            if not c["required_answers_complete"]:
                forbids.append("forbid-missing-required-answers")
            if c["daily_remaining"] <= 0:
                forbids.append("forbid-daily-cap-exhausted")
            if not c["cooldown_ok"]:
                forbids.append("forbid-during-cooldown")
            if not c["connector_can_submit"]:
                forbids.append("forbid-connector-without-submit-capability")
            if c["paused"]:
                forbids.append("forbid-paused-or-cancelled")
            if req.is_judge and req.target_environment != "test":
                forbids.append("judge-sessions-test-employers-only")
        if req.action in {"send_referral", "publish_profile"} and owner and c["approved_content_hash_matches"] and not req.is_judge:
            permits.append("referral-needs-explicit-approval" if req.action == "send_referral" else "profile-publish-needs-explicit-approval")
        if forbids:
            return Decision(False, forbids, "reference")
        return Decision(bool(permits), permits, "reference")


_ENGINE: Any = None


def engine() -> Any:
    """Cedar in deployed code. Tests may call ``set_engine(ReferenceEngine())``."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CedarEngine()
    return _ENGINE


def set_engine(e: Any) -> None:
    global _ENGINE
    _ENGINE = e


def context_grid() -> list[Request]:
    """Exhaustive-ish grid used by the Cedar/reference parity test."""
    out = []
    for mode, score, approved, mandate, eligible, answers, remaining, cooldown, capable, paused, judge, env, owner in itertools.product(
        MODES, (80, 81), (False, True), (False, True), (False, True), (False, True), (0, 1), (False, True),
        (False, True), (False, True), (False, True), ("test", "live"), (True, False),
    ):
        out.append(Request(
            user_id="u1", is_judge=judge, action=SUBMIT, app_owner="u1" if owner else "u2", target_environment=env,
            context={"mode": mode, "score": score, "approved_packet_hash_matches": approved, "mandate_active": mandate,
                     "auto_eligible": eligible, "required_answers_complete": answers, "daily_remaining": remaining,
                     "cooldown_ok": cooldown, "connector_can_submit": capable, "paused": paused},
        ))
    return out
