"""Application workflow: records, state machine, approvals, quotas and the submission gate.

Invariants enforced here (not in prompts):
* A workflow state change and its outbox message commit in one transaction.
* Submission requires a fresh Cedar decision computed from live DynamoDB facts.
* Daily capacity is reserved atomically before the external write; unknown
  outcomes keep consuming capacity until reconciled.
* Once an attempt is marked dispatched, no worker may click Submit again for it;
  a replacement worker reconciles instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import connectors, policy
from .store import And, C, ConditionFailed, Or, Put, Store, Update
from .util import Clock, canonical_json, local_date, new_id, sha256

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


def U(uid: str) -> str:
    return f"USER#{uid}"


STATES = {
    "Discovered", "Ineligible", "Preparing", "NeedsInformation", "NeedsApproval", "NeedsUserPresence", "Authorized", "ManualHandoff",
    "Queued", "Paused", "Submitting", "Submitted", "KnownFailure", "OutcomeUnknown", "NeedsReview", "Withdrawn",
}

TRANSITIONS: dict[str, set[str]] = {
    "Discovered": {"Ineligible", "Preparing", "Withdrawn"},
    "Ineligible": {"Preparing", "Withdrawn"},
    "Preparing": {"NeedsInformation", "NeedsApproval", "NeedsUserPresence", "Authorized", "ManualHandoff", "Withdrawn"},
    "NeedsInformation": {"Preparing", "Withdrawn"},
    "NeedsApproval": {"Authorized", "Preparing", "Withdrawn"},
    "NeedsUserPresence": {"Submitting", "Preparing", "Withdrawn"},
    "ManualHandoff": {"Submitted", "Preparing", "Withdrawn"},
    "Authorized": {"Queued", "Preparing", "Paused", "Withdrawn"},
    "Queued": {"Submitting", "Paused", "Preparing", "NeedsApproval", "Withdrawn"},
    "Paused": {"Queued", "Preparing", "Withdrawn"},
    "Submitting": {"Submitted", "KnownFailure", "OutcomeUnknown", "Preparing", "Queued", "NeedsUserPresence"},
    "OutcomeUnknown": {"Submitted", "NeedsReview"},
    "NeedsReview": {"Submitted", "Preparing", "Withdrawn"},
    "KnownFailure": {"Preparing", "Withdrawn"},
    "Submitted": set(),
    "Withdrawn": set(),
}

STAGES = ("applied", "reply_received", "assessment_invited", "interview_scheduled", "offer", "rejected", "withdrawn")

DEFAULT_SETTINGS = {
    "mode": "review",  # review | auto_above_80 | auto_eligible
    "daily_cap": 5,
    "cooldown_seconds": 120,
    "timezone": "Asia/Kolkata",
    "mandate": None,  # {enabled, scope:{sources, min_score}, expires_at, policy_version, created_at}
    "notify_email": None,
    "notify_email_verified": False,
    "telegram_chat_id": None,
    "voice_enabled": True,
    "preferences": {"roles": [], "locations": [], "work_modes": [], "excluded_companies": [], "min_salary": None},
}


def _packet_submission_mode(packet: dict | None, connector: str) -> str:
    """Resolve packet/2 submission strategy with packet/1 compatibility."""
    target = (((packet or {}).get("body") or {}).get("target")
              if "body" in (packet or {}) else (packet or {}).get("target")) or {}
    plan = target.get("submission") or {}
    if plan.get("mode"):
        return str(plan["mode"])
    legacy_can_submit = connectors.can(connector, "submit") and bool(target.get("submittable", True))
    return "cloud_browser" if legacy_can_submit else "manual"


class WorkflowError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class Principal:
    user_id: str
    is_judge: bool = False
    email: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class Workflow:
    def __init__(self, store: Store, clock: Clock | None = None) -> None:
        self.store = store
        self.clock = clock or Clock()

    # ---- generic helpers ---------------------------------------------------

    def _now_iso(self) -> str:
        return self.clock.iso()

    def event_put(self, uid: str, etype: str, data: dict, app_id: str | None = None, correlation_id: str | None = None) -> Put:
        ts = self._now_iso()
        eid = new_id("ev_")
        item = {
            "pk": U(uid), "sk": f"EVENT#{ts}#{eid}", "type": etype, "event_id": eid, "at": ts,
            "data": data, "app_id": app_id, "correlation_id": correlation_id, "entity": "event",
            "ttl": int(self.clock.now()) + 60 * 60 * 24 * 60,
        }
        if app_id:
            item["gsi1pk"] = f"APPTL#{app_id}"
            item["gsi1sk"] = f"{ts}#{eid}"
        return Put(item, C("pk", "not_exists"))

    def outbox_put(self, queue: str, message: dict, dedupe_key: str, group: str | None = None) -> Put:
        """Outbox item: a DynamoDB Stream wakes the relay; a scheduled repair re-sends stragglers."""
        ts = self._now_iso()
        oid = sha256(dedupe_key)[:32]
        return Put({
            "pk": f"OUTBOX#{oid}", "sk": "OUTBOX", "entity": "outbox", "queue": queue, "message": message,
            "dedupe_key": dedupe_key, "group": group, "status": "pending", "created_at": ts,
            "gsi1pk": "OUTBOX#pending", "gsi1sk": ts, "attempts": 0,
            "ttl": int(self.clock.now()) + 60 * 60 * 24 * 14,
        }, C("pk", "not_exists"))

    def settings(self, uid: str) -> dict:
        item = self.store.get(U(uid), "SETTINGS") or {}
        merged = {**DEFAULT_SETTINGS, **{k: v for k, v in item.items() if k not in ("pk", "sk")}}
        merged["preferences"] = {**DEFAULT_SETTINGS["preferences"], **(item.get("preferences") or {})}
        return merged

    def update_settings(self, uid: str, changes: dict) -> dict:
        allowed = {"mode", "daily_cap", "cooldown_seconds", "timezone", "notify_email", "voice_enabled", "preferences"}
        clean = {k: v for k, v in changes.items() if k in allowed}
        if "mode" in clean and clean["mode"] not in policy.MODES:
            raise WorkflowError("invalid_mode", "mode must be review, auto_above_80 or auto_eligible", 400)
        if "daily_cap" in clean:
            clean["daily_cap"] = max(0, min(25, int(clean["daily_cap"])))
        if "cooldown_seconds" in clean:
            clean["cooldown_seconds"] = max(30, min(3600, int(clean["cooldown_seconds"])))
        if "notify_email" in clean:
            clean["notify_email_verified"] = False
        if not clean:
            return self.settings(uid)
        clean["updated_at"] = self._now_iso()
        self.store.transact([
            Update(U(uid), "SETTINGS", set=clean),
            self.event_put(uid, "settings.updated", {"fields": sorted(clean.keys())}),
        ])
        return self.settings(uid)

    # ---- mandates -------------------------------------------------------------

    def set_mandate(self, p: Principal, enabled: bool, mode: str | None = None, hours: int = 72,
                    scope: dict | None = None) -> dict:
        now = self.clock.now()
        if enabled:
            if mode not in ("auto_above_80", "auto_eligible"):
                raise WorkflowError("invalid_mode", "a mandate is only needed for automatic modes", 400)
            mandate = {
                "enabled": True, "mode": mode, "scope": scope or {"connectors": ["northwind-test-portal"]},
                "expires_at": now + max(1, min(hours, 24 * 30)) * 3600, "policy_version": policy.POLICY_VERSION,
                "created_at": self._now_iso(), "mandate_id": new_id("md_"),
            }
            sets = {"mandate": mandate, "mode": mode}
            etype = "mandate.granted"
        else:
            mandate = None
            sets = {"mandate": None, "mode": "review"}
            etype = "mandate.revoked"
        self.store.transact([
            Update(U(p.user_id), "SETTINGS", set=sets),
            self.event_put(p.user_id, etype, {"mode": sets["mode"], "expires_at": (mandate or {}).get("expires_at")}),
        ])
        return self.settings(p.user_id)

    def mandate_active(self, settings: dict, connector: str) -> bool:
        m = settings.get("mandate") or {}
        return bool(
            m.get("enabled")
            and m.get("mode") == settings.get("mode")
            and m.get("policy_version") == policy.POLICY_VERSION
            and float(m.get("expires_at", 0)) > self.clock.now()
            and connector in (m.get("scope") or {}).get("connectors", [])
        )

    # ---- applications ---------------------------------------------------------

    def get_app(self, uid: str, app_id: str) -> dict:
        app = self.store.get(U(uid), f"APP#{app_id}")
        if not app:
            raise WorkflowError("not_found", "application not found", 404)
        return app

    def list_apps(self, uid: str) -> list[dict]:
        return self.store.query(U(uid), "APP#", limit=500)

    def _transition(self, app: dict, to: str, extra: dict | None = None) -> Update:
        frm = app["action_state"]
        if to not in TRANSITIONS.get(frm, set()):
            raise WorkflowError("invalid_transition", f"{frm} -> {to} is not allowed")
        sets = {"action_state": to, "updated_at": self._now_iso(), "version": app["version"] + 1, **(extra or {})}
        return Update(app["pk"], app["sk"], set=sets,
                      condition=And(C("version", "eq", app["version"]), C("action_state", "eq", frm)))

    def create_application(self, uid: str, job: dict, match: dict, connector: str) -> dict:
        """Idempotent per (user, canonical requisition)."""
        canonical = job.get("canonical_key") or job["job_key"]
        existing = self.store.get(U(uid), f"APPKEY#{canonical}")
        if existing:
            return self.get_app(uid, existing["app_id"])
        app_id = new_id("app_")
        now = self._now_iso()
        app = {
            "pk": U(uid), "sk": f"APP#{app_id}", "entity": "application", "app_id": app_id, "user_id": uid,
            "job_key": job["job_key"], "canonical_key": canonical, "company": job.get("company"), "title": job.get("title"),
            "location": job.get("location"), "url": job.get("url"), "source": job.get("source"), "connector": connector,
            "target_environment": connectors.environment(connector), "action_state": "Discovered",
            "recruitment_stage": None, "score": match.get("score", 0), "auto_eligible": bool(match.get("auto_eligible")),
            "blocked": bool(match.get("blocked")), "packet_version": 0, "packet_hash": None, "approved_hash": None,
            "version": 1, "paused": False, "created_at": now, "updated_at": now,
        }
        try:
            self.store.transact([
                Put({"pk": U(uid), "sk": f"APPKEY#{canonical}", "app_id": app_id, "entity": "appkey"}, C("pk", "not_exists")),
                Put(app, C("pk", "not_exists")),
                self.event_put(uid, "application.discovered", {"company": app["company"], "title": app["title"], "score": app["score"]}, app_id),
            ])
        except ConditionFailed:
            existing = self.store.get(U(uid), f"APPKEY#{canonical}")
            if existing:
                return self.get_app(uid, existing["app_id"])
            raise
        return app

    def save_packet(self, uid: str, app_id: str, packet: dict, settings: dict | None = None) -> dict:
        """Persist an immutable packet version and route to NeedsInformation / NeedsApproval / Authorized."""
        app = self.get_app(uid, app_id)
        settings = settings or self.settings(uid)
        if app["action_state"] not in ("Discovered", "Ineligible", "Preparing", "NeedsInformation", "NeedsApproval",
                                        "KnownFailure", "NeedsReview", "Authorized", "Queued", "Paused", "NeedsUserPresence", "ManualHandoff"):
            raise WorkflowError("invalid_state", f"cannot prepare in state {app['action_state']}")
        # move into Preparing first (single hop from any preparable state)
        if app["action_state"] != "Preparing":
            self.store.transact([self._transition(app, "Preparing")])
            app = self.get_app(uid, app_id)

        version = app["packet_version"] + 1
        body = {k: packet[k] for k in ("target", "job_snapshot_hash", "profile_version", "resume_key", "answers",
                                        "attachments", "consents", "form_signature", "cover_note") if k in packet}
        packet_hash = sha256(body)
        missing = [q for q in packet.get("unknown_required", [])]
        item = {
            "pk": U(uid), "sk": f"PACKET#{app_id}#{version:04d}", "entity": "packet", "app_id": app_id,
            "version": version, "hash": packet_hash, "body": body, "unknown_required": missing,
            "schema_version": "packet/1", "created_at": self._now_iso(), "field_evidence": packet.get("field_evidence", {}),
            "fields": packet.get("fields", []),
        }
        target_info = packet.get("target") or {}
        plan = target_info.get("submission") or {}
        mode = _packet_submission_mode(packet, app["connector"])
        can_submit = mode == "cloud_browser" and bool(plan.get("can_submit", True))
        if missing:
            target = "NeedsInformation"
        elif mode == "local_browser":
            # Authenticated portals are real submission targets, but the final
            # write must still satisfy the same explicit-approval/mandate policy
            # as the cloud browser. In review mode this therefore waits for
            # approval; in an authorized auto mode it becomes ready for the
            # local companion immediately.
            decision = self.decide_submission(
                Principal(uid), app | {"packet_hash": packet_hash, "approved_hash": None},
                settings, reserve_check=True, packet={"body": packet, "unknown_required": missing},
            )
            target = "NeedsUserPresence" if decision.allowed else "NeedsApproval"
        elif not can_submit:
            target = "ManualHandoff"
        elif settings["mode"] == "review":
            target = "NeedsApproval"
        else:
            decision = self.decide_submission(Principal(uid), app | {"packet_hash": packet_hash, "approved_hash": None}, settings,
                                              reserve_check=True)
            target = "Authorized" if decision.allowed else "NeedsApproval"
        extra = {"packet_version": version, "packet_hash": packet_hash, "approved_hash": None,
                 "unknown_required": missing, "mode_at_decision": settings["mode"]}
        ops: list[Any] = [Put(item, C("pk", "not_exists")), self._transition(app, target, extra),
                          self.event_put(uid, "packet.prepared", {"version": version, "hash": packet_hash[:12], "next": target,
                                                                   "unknown_required": missing}, app_id)]
        if target == "NeedsApproval":
            ops.append(self.outbox_put("notify", {"kind": "approval_requested", "user_id": uid, "app_id": app_id,
                                                  "packet_hash": packet_hash}, f"notify:approval:{app_id}:{version}"))
        if target == "NeedsInformation":
            ops.append(self.outbox_put("notify", {"kind": "information_needed", "user_id": uid, "app_id": app_id,
                                                  "questions": missing}, f"notify:info:{app_id}:{version}"))
        if target == "Authorized":
            ops += self._queue_ops(uid, app_id, packet_hash)
        self.store.transact(ops)
        if target == "Authorized":
            self._mark_queued(uid, app_id)
        return self.get_app(uid, app_id)

    def latest_packet(self, uid: str, app_id: str) -> dict | None:
        rows = self.store.query(U(uid), f"PACKET#{app_id}#", limit=1, newest_first=True)
        return rows[0] if rows else None

    # ---- approval ------------------------------------------------------------

    def approve(self, p: Principal, app_id: str, packet_hash: str, channel: str) -> dict:
        """Explicit approval bound to one packet hash. Repeated clicks return the existing result."""
        app = self.get_app(p.user_id, app_id)
        d = policy.engine().authorize(policy.Request(p.user_id, p.is_judge, "approve_application", app["user_id"],
                                                     app["target_environment"], {}))
        if not d.allowed:
            raise WorkflowError("forbidden", "not allowed", 403)
        if app.get("approved_hash") == packet_hash:
            return app  # idempotent repeat
        if app["packet_hash"] != packet_hash:
            raise WorkflowError("stale_packet", "this approval refers to an older version of the application; review the current one")
        if app["action_state"] != "NeedsApproval":
            raise WorkflowError("invalid_state", f"application is {app['action_state']}, not awaiting approval")
        approval = {"pk": U(p.user_id), "sk": f"APPROVAL#{app_id}#{packet_hash[:24]}", "entity": "approval",
                    "app_id": app_id, "packet_hash": packet_hash, "channel": channel, "at": self._now_iso(),
                    "policy_version": policy.POLICY_VERSION}
        packet = self.latest_packet(p.user_id, app_id)
        mode = _packet_submission_mode(packet, app["connector"])
        next_state = "NeedsUserPresence" if mode == "local_browser" else "Authorized"
        ops = [
            Put(approval, C("pk", "not_exists")),
            self._transition(app, next_state, {"approved_hash": packet_hash}),
            self.event_put(p.user_id, "application.approved",
                           {"channel": channel, "hash": packet_hash[:12], "submission_mode": mode}, app_id),
        ]
        if mode == "cloud_browser":
            ops += self._queue_ops(p.user_id, app_id, packet_hash)
        try:
            self.store.transact(ops)
        except ConditionFailed:
            app2 = self.get_app(p.user_id, app_id)
            if app2.get("approved_hash") == packet_hash:
                return app2
            raise WorkflowError("conflict", "application changed while approving; refresh and retry") from None
        if mode == "cloud_browser":
            self._mark_queued(p.user_id, app_id)
        return self.get_app(p.user_id, app_id)

    def local_browser_start(self, p: Principal, app_id: str, packet_hash: str) -> dict:
        """Reserve policy capacity for one approved authenticated-browser run."""
        app = self.get_app(p.user_id, app_id)
        if app["action_state"] == "Submitting" and app.get("local_browser_packet_hash") == packet_hash:
            return app
        if app["action_state"] != "NeedsUserPresence":
            raise WorkflowError("invalid_state", f"application is {app['action_state']}, not ready for the browser companion")
        if app.get("packet_hash") != packet_hash:
            raise WorkflowError("stale_packet", "application packet changed; refresh before submitting")
        settings = self.settings(p.user_id)
        packet = self.latest_packet(p.user_id, app_id)
        decision = self.decide_submission(p, app, settings, packet=packet)
        if not decision.allowed:
            raise WorkflowError("forbidden", "submission policy no longer allows this application", 403)

        ledger_sk = self.ledger_key(p.user_id, settings)
        cap = int(settings.get("daily_cap", 5))
        now = self.clock.now()
        cooldown = int(settings.get("cooldown_seconds", 120))
        attempt_id = new_id("local_")
        try:
            self.store.transact([
                Update(U(p.user_id), ledger_sk,
                       set={"cap": cap, "timezone": settings["timezone"], "last_submit_at": now},
                       add={"used": 1, "reserved": 1},
                       condition=And(Or(C("used", "not_exists"), C("used", "lt", cap)),
                                     Or(C("last_submit_at", "not_exists"), C("last_submit_at", "le", now - cooldown)))),
                self._transition(app, "Submitting", {
                    "current_attempt": attempt_id,
                    "local_browser_packet_hash": packet_hash,
                    "local_browser_ledger": ledger_sk,
                    "last_decision": decision.to_dict(),
                }),
                self.event_put(p.user_id, "submission.local_started",
                               {"attempt_id": attempt_id, "packet_hash": packet_hash[:12]}, app_id),
            ])
        except ConditionFailed:
            raise WorkflowError("rate_limited", "daily application cap or cooldown is currently blocking submission", 409) from None
        return self.get_app(p.user_id, app_id)

    def local_browser_dispatch(self, p: Principal, app_id: str, packet_hash: str) -> dict:
        """Record the external-write boundary immediately before the companion clicks Submit."""
        app = self.get_app(p.user_id, app_id)
        if app["action_state"] != "Submitting" or app.get("local_browser_packet_hash") != packet_hash:
            raise WorkflowError("invalid_state", "browser session is not the current submission")
        if app.get("local_browser_dispatched_at"):
            return app
        now = self._now_iso()
        self.store.transact([
            Update(app["pk"], app["sk"],
                   set={"local_browser_dispatched_at": now, "updated_at": now, "version": app["version"] + 1},
                   condition=And(C("version", "eq", app["version"]), C("action_state", "eq", "Submitting"))),
            self.event_put(p.user_id, "submission.local_dispatched", {"packet_hash": packet_hash[:12]}, app_id),
        ])
        return self.get_app(p.user_id, app_id)

    def local_browser_complete(self, p: Principal, app_id: str, packet_hash: str, outcome: str,
                               receipt: dict | None = None, reason: str | None = None) -> dict:
        app = self.get_app(p.user_id, app_id)
        if app["action_state"] == "Submitted":
            return app
        if app["action_state"] != "Submitting" or app.get("local_browser_packet_hash") != packet_hash:
            raise WorkflowError("invalid_state", "this browser completion does not match the current submission")
        now = self._now_iso()
        ledger = app.get("local_browser_ledger") or self.ledger_key(p.user_id, self.settings(p.user_id))
        dispatched = bool(app.get("local_browser_dispatched_at"))

        if outcome == "submitted":
            ref = (receipt or {}).get("reference") or f"browser-{sha256([app_id, packet_hash, now])[:14]}"
            real_receipt = {**(receipt or {}), "reference": ref, "submitted_at": (receipt or {}).get("submitted_at") or now,
                            "provider": (receipt or {}).get("provider") or "authenticated-browser"}
            ops = [
                Update(U(p.user_id), ledger, add={"reserved": -1, "submitted": 1}),
                self._transition(app, "Submitted", {
                    "receipt": real_receipt, "recruitment_stage": "applied", "submitted_at": now,
                }),
                self.event_put(p.user_id, "submission.succeeded",
                               {"reference": ref, "via": "authenticated-browser"}, app_id),
            ]
        elif outcome == "needs_user":
            # No write has happened yet. Release the reservation so login/MFA or
            # an unanswered employer question never consumes the daily cap.
            if dispatched:
                raise WorkflowError("invalid_outcome", "user attention cannot be requested after submit was dispatched", 409)
            ops = [
                Update(U(p.user_id), ledger, add={"used": -1, "reserved": -1}),
                self._transition(app, "NeedsUserPresence", {"last_error": (reason or "browser needs your attention")[:300]}),
                self.event_put(p.user_id, "submission.user_presence_needed",
                               {"reason": (reason or "")[:300]}, app_id),
            ]
        elif outcome == "known_failure":
            ledger_delta = {"reserved": -1, "rejected": 1} if dispatched else {"used": -1, "reserved": -1}
            ops = [
                Update(U(p.user_id), ledger, add=ledger_delta),
                self._transition(app, "KnownFailure", {"last_error": (reason or "submission failed")[:300]}),
                self.event_put(p.user_id, "submission.failed", {"reason": (reason or "")[:300]}, app_id),
            ]
        else:
            if not dispatched:
                ops = [
                    Update(U(p.user_id), ledger, add={"used": -1, "reserved": -1}),
                    self._transition(app, "NeedsUserPresence", {"last_error": (reason or "browser stopped before submit")[:300]}),
                    self.event_put(p.user_id, "submission.user_presence_needed", {"reason": (reason or "")[:300]}, app_id),
                ]
            else:
                ops = [
                    Update(U(p.user_id), ledger, add={"reserved": -1, "uncertain": 1}),
                    self._transition(app, "OutcomeUnknown", {"last_error": (reason or "submission outcome unknown")[:300]}),
                    self.event_put(p.user_id, "submission.outcome_unknown", {"reason": (reason or "")[:300]}, app_id),
                ]
        self.store.transact(ops)
        return self.get_app(p.user_id, app_id)

    def reject(self, p: Principal, app_id: str, reason: str = "") -> dict:
        app = self.get_app(p.user_id, app_id)
        self.store.transact([self._transition(app, "Withdrawn", {"withdrawn_reason": reason[:200]}),
                             self.event_put(p.user_id, "application.withdrawn", {"reason": reason[:200]}, app_id)])
        return self.get_app(p.user_id, app_id)

    def _queue_ops(self, uid: str, app_id: str, packet_hash: str) -> list:
        attempt_id = new_id("att_")
        return [self.outbox_put("submit", {"kind": "submit", "user_id": uid, "app_id": app_id, "attempt_id": attempt_id,
                                           "packet_hash": packet_hash}, f"submit:{app_id}:{attempt_id}", group=uid)]

    def _mark_queued(self, uid: str, app_id: str) -> None:
        app = self.get_app(uid, app_id)
        if app["action_state"] == "Authorized":
            try:
                self.store.transact([self._transition(app, "Queued"),
                                     self.event_put(uid, "application.queued", {}, app_id)])
            except ConditionFailed:
                pass

    def pause(self, p: Principal, app_id: str) -> dict:
        app = self.get_app(p.user_id, app_id)
        if app["action_state"] in ("Submitting",):
            raise WorkflowError("external_write_started", "the browser has already started this submission; it cannot be paused now")
        self.store.transact([self._transition(app, "Paused", {"paused": True}),
                             self.event_put(p.user_id, "application.paused", {}, app_id)])
        return self.get_app(p.user_id, app_id)

    def resume(self, p: Principal, app_id: str) -> dict:
        app = self.get_app(p.user_id, app_id)
        if app["action_state"] != "Paused":
            raise WorkflowError("invalid_state", "not paused")
        self.store.transact([self._transition(app, "Queued", {"paused": False}),
                             self.event_put(p.user_id, "application.resumed", {}, app_id),
                             *self._queue_ops(p.user_id, app_id, app["packet_hash"])])
        return self.get_app(p.user_id, app_id)

    # ---- authorization --------------------------------------------------------

    def ledger_key(self, uid: str, settings: dict) -> str:
        return f"LEDGER#{local_date(self.clock.now(), settings.get('timezone') or 'UTC')}"

    def decide_submission(self, p: Principal, app: dict, settings: dict, reserve_check: bool = False,
                          packet: dict | None = None) -> policy.Decision:
        ledger = self.store.get(U(p.user_id), self.ledger_key(p.user_id, settings)) or {}
        used = int(ledger.get("used", 0))
        cap = int(settings.get("daily_cap", 5))
        last = float(ledger.get("last_submit_at", 0) or settings.get("last_submit_at", 0) or 0)
        cooldown_ok = (self.clock.now() - last) >= int(settings.get("cooldown_seconds", 120)) if last else True
        unknown = (packet or {}).get("unknown_required") if packet else app.get("unknown_required")
        ctx = {
            "mode": settings.get("mode", "review"),
            "score": int(app.get("score") or 0),
            "approved_packet_hash_matches": bool(app.get("approved_hash")) and app.get("approved_hash") == app.get("packet_hash"),
            "mandate_active": self.mandate_active(settings, app["connector"]),
            "auto_eligible": bool(app.get("auto_eligible")) and not app.get("blocked"),
            "required_answers_complete": not unknown,
            "daily_remaining": cap - used,
            "cooldown_ok": True if reserve_check else cooldown_ok,
            "connector_can_submit": (
                _packet_submission_mode(packet, app["connector"]) in ("cloud_browser", "local_browser")
                if packet else connectors.can(app["connector"], "submit")
            ),
            "paused": bool(app.get("paused")),
        }
        return policy.engine().authorize(policy.Request(p.user_id, p.is_judge, policy.SUBMIT, app["user_id"],
                                                        app["target_environment"], ctx))

    # ---- submission gate (called by the browser worker) -----------------------

    def gate_begin(self, p: Principal, app_id: str, attempt_id: str, packet_hash: str, lease_seconds: int = 240) -> dict:
        """Final pre-dispatch check + atomic quota reservation + lease acquisition."""
        app = self.get_app(p.user_id, app_id)
        existing = self.store.get(U(p.user_id), f"ATTEMPT#{app_id}#{attempt_id}")
        if existing:
            if existing.get("dispatched_at") and not existing.get("outcome"):
                return {"action": "reconcile", "attempt": existing}
            if existing.get("outcome"):
                return {"action": "done", "attempt": existing}
            if float(existing.get("lease_until", 0)) > self.clock.now():
                return {"action": "busy"}
            return self._recover_stale_attempt(p.user_id, app, existing)
        if app["action_state"] == "Submitted":
            return {"action": "done"}
        if app["action_state"] == "OutcomeUnknown":
            return {"action": "reconcile", "attempt": self._latest_attempt(p.user_id, app_id)}
        if app["action_state"] not in ("Queued",):
            return {"action": "skip", "reason": f"state is {app['action_state']}"}
        if app["packet_hash"] != packet_hash:
            return {"action": "skip", "reason": "packet changed after queueing"}
        settings = self.settings(p.user_id)
        packet = self.latest_packet(p.user_id, app_id)
        decision = self.decide_submission(p, app, settings, packet=packet)
        if not decision.allowed:
            # Classify the denial from facts, not from engine-specific reason strings.
            if self.decide_submission(p, app, settings, packet=packet, reserve_check=True).allowed:
                return {"action": "denied", "decision": decision.to_dict(), "retry_later": True}  # only the cooldown blocks
            ledger_now = self.store.get(U(p.user_id), self.ledger_key(p.user_id, settings)) or {}
            cap_hit = int(ledger_now.get("used", 0)) >= int(settings.get("daily_cap", 5))
            to = "Paused" if cap_hit else "NeedsApproval"
            ops = [self._transition(app, to, {"last_decision": decision.to_dict(), "paused": to == "Paused"}),
                   self.event_put(p.user_id, "submission.denied", decision.to_dict(), app_id)]
            try:
                self.store.transact(ops)
            except ConditionFailed:
                pass
            return {"action": "denied", "decision": decision.to_dict(), "retry_later": False}

        ledger_sk = self.ledger_key(p.user_id, settings)
        cap = int(settings["daily_cap"])
        now = self.clock.now()
        lease_until = now + lease_seconds
        fencing = int(app["version"]) + 1
        attempt = {
            "pk": U(p.user_id), "sk": f"ATTEMPT#{app_id}#{attempt_id}", "entity": "attempt", "app_id": app_id,
            "attempt_id": attempt_id, "packet_hash": packet_hash, "lease_until": lease_until, "fencing": fencing,
            "ledger": ledger_sk, "started_at": self._now_iso(), "decision": decision.to_dict(),
        }
        cooldown = int(settings["cooldown_seconds"])
        try:
            self.store.transact([
                Update(U(p.user_id), ledger_sk, set={"cap": cap, "timezone": settings["timezone"], "last_submit_at": now},
                       add={"used": 1, "reserved": 1},
                       condition=And(Or(C("used", "not_exists"), C("used", "lt", cap)),
                                     Or(C("last_submit_at", "not_exists"), C("last_submit_at", "le", now - cooldown)))),
                Put(attempt, C("pk", "not_exists")),
                self._transition(app, "Submitting", {"current_attempt": attempt_id, "fencing": fencing}),
                self.event_put(p.user_id, "submission.started", {"attempt_id": attempt_id, "decision": decision.reasons}, app_id),
            ])
        except ConditionFailed:
            fresh = self.get_app(p.user_id, app_id)
            if fresh["action_state"] != "Queued":
                return {"action": "skip", "reason": f"state is {fresh['action_state']}"}
            ledger = self.store.get(U(p.user_id), ledger_sk) or {}
            if int(ledger.get("used", 0)) >= cap:
                self.store.transact([self._transition(fresh, "Paused", {"paused": True}),
                                     self.event_put(p.user_id, "submission.denied", {"reasons": ["daily cap reached"]}, app_id)])
                return {"action": "denied", "decision": {"allowed": False, "reasons": ["forbid-daily-cap-exhausted"]}}
            return {"action": "denied", "decision": {"allowed": False, "reasons": ["forbid-during-cooldown"]}, "retry_later": True}
        return {"action": "proceed", "attempt": attempt, "packet": packet, "app": self.get_app(p.user_id, app_id)}

    def _recover_stale_attempt(self, uid: str, app: dict, attempt: dict) -> dict:
        """Worker died BEFORE the external write boundary: release capacity and requeue with a new attempt."""
        if app["action_state"] != "Submitting" or app.get("current_attempt") != attempt["attempt_id"]:
            return {"action": "skip", "reason": "stale attempt no longer current"}
        try:
            self.store.transact([
                Update(U(uid), attempt["sk"], set={"outcome": "abandoned_before_dispatch", "finished_at": self._now_iso()},
                       condition=And(C("dispatched_at", "not_exists"), C("outcome", "not_exists"))),
                Update(U(uid), attempt["ledger"], add={"used": -1, "reserved": -1}),
                self._transition(app, "Queued"),
                self.event_put(uid, "submission.requeued", {"reason": "worker lease expired before submit"}, app["app_id"]),
                *self._queue_ops(uid, app["app_id"], app["packet_hash"]),
            ])
        except ConditionFailed:
            return {"action": "busy"}
        return {"action": "requeued"}

    def _attempt(self, uid: str, app_id: str, attempt_id: str) -> dict:
        a = self.store.get(U(uid), f"ATTEMPT#{app_id}#{attempt_id}")
        if not a:
            raise WorkflowError("not_found", "attempt not found", 404)
        return a

    def _latest_attempt(self, uid: str, app_id: str) -> dict | None:
        rows = self.store.query(U(uid), f"ATTEMPT#{app_id}#", limit=1, newest_first=True)
        return rows[0] if rows else None

    def gate_dispatch(self, uid: str, app_id: str, attempt_id: str, fencing: int, form_signature: str) -> dict:
        """Record the external-write boundary immediately before clicking Submit."""
        a = self._attempt(uid, app_id, attempt_id)
        packet = self.latest_packet(uid, app_id) or {}
        expected = (packet.get("body") or {}).get("form_signature")
        if expected and form_signature != expected:
            app = self.get_app(uid, app_id)
            self.store.transact([
                Update(U(uid), a["sk"], set={"outcome": "form_changed", "finished_at": self._now_iso()}, add={},
                       condition=C("fencing", "eq", fencing)),
                Update(U(uid), a["ledger"], add={"used": -1, "reserved": -1}),
                self._transition(app, "Preparing", {"invalidated_reason": "required form fields changed"}),
                self.event_put(uid, "submission.form_changed", {"expected": expected[:12], "found": form_signature[:12]}, app_id),
                self.outbox_put("work", {"kind": "prepare", "user_id": uid, "app_id": app_id}, f"work:reprepare:{app_id}:{attempt_id}"),
            ])
            return {"action": "abort", "reason": "form_changed"}
        try:
            self.store.update(Update(U(uid), a["sk"], set={"dispatched_at": self._now_iso()},
                                     condition=And(C("fencing", "eq", fencing), C("dispatched_at", "not_exists"),
                                                   C("lease_until", "gt", self.clock.now()))))
        except ConditionFailed:
            return {"action": "abort", "reason": "lease lost or already dispatched"}
        return {"action": "submit"}

    def gate_complete(self, uid: str, app_id: str, attempt_id: str, outcome: str, receipt: dict | None = None,
                      reason: str | None = None, evidence_key: str | None = None) -> dict:
        """outcome: submitted | known_failure | unknown."""
        a = self._attempt(uid, app_id, attempt_id)
        if a.get("outcome"):
            return {"action": "noop", "outcome": a["outcome"]}
        app = self.get_app(uid, app_id)
        now = self._now_iso()
        if outcome == "submitted":
            if not receipt or not receipt.get("reference"):
                raise WorkflowError("missing_receipt", "success requires a provider receipt/reference", 400)
            ops = [
                Update(U(uid), a["sk"], set={"outcome": "submitted", "receipt": receipt, "evidence_key": evidence_key, "finished_at": now},
                       condition=C("outcome", "not_exists")),
                Update(U(uid), a["ledger"], add={"reserved": -1, "submitted": 1}),
                self._transition(app, "Submitted", {"receipt": receipt, "recruitment_stage": "applied", "submitted_at": now,
                                                    "evidence_key": evidence_key}),
                self.event_put(uid, "submission.succeeded", {"reference": receipt.get("reference")}, app_id),
                Put({"pk": f"RECEIPT#{receipt['reference']}", "sk": "RECEIPT", "user_id": uid, "app_id": app_id}),
                self.outbox_put("notify", {"kind": "submitted", "user_id": uid, "app_id": app_id, "reference": receipt.get("reference")},
                                f"notify:submitted:{app_id}"),
            ]
        elif outcome == "known_failure":
            ops = [
                Update(U(uid), a["sk"], set={"outcome": "known_failure", "reason": reason, "finished_at": now},
                       condition=C("outcome", "not_exists")),
                self._transition(app, "KnownFailure", {"last_error": reason}),
                self.event_put(uid, "submission.failed", {"reason": reason}, app_id),
                self.outbox_put("notify", {"kind": "failed", "user_id": uid, "app_id": app_id, "reason": reason},
                                f"notify:failed:{app_id}:{attempt_id}"),
            ]
            # capacity is released only if the external write never started
            if not a.get("dispatched_at"):
                ops.insert(1, Update(U(uid), a["ledger"], add={"used": -1, "reserved": -1}))
            else:
                ops.insert(1, Update(U(uid), a["ledger"], add={"reserved": -1, "rejected": 1}))
        elif outcome == "unknown":
            ops = [
                Update(U(uid), a["sk"], set={"outcome_pending": "unknown", "unknown_at": now}),
                Update(U(uid), a["ledger"], add={"reserved": -1, "uncertain": 1}),
                self._transition(app, "OutcomeUnknown", {"last_error": reason or "no confirmation received"}),
                self.event_put(uid, "submission.outcome_unknown", {"reason": reason}, app_id),
                self.outbox_put("work", {"kind": "reconcile", "user_id": uid, "app_id": app_id, "attempt_id": attempt_id},
                                f"work:reconcile:{app_id}:{attempt_id}"),
            ]
        else:
            raise WorkflowError("bad_outcome", outcome, 400)
        try:
            self.store.transact(ops)
        except ConditionFailed:
            return {"action": "noop"}
        return {"action": "recorded", "state": self.get_app(uid, app_id)["action_state"]}

    def reconcile(self, uid: str, app_id: str, attempt_id: str, found_receipt: dict | None) -> dict:
        """Resolve OutcomeUnknown from provider evidence. Never resubmits."""
        app = self.get_app(uid, app_id)
        if app["action_state"] != "OutcomeUnknown":
            return {"action": "noop", "state": app["action_state"]}
        a = self._attempt(uid, app_id, attempt_id)
        now = self._now_iso()
        if found_receipt:
            ops = [
                Update(U(uid), a["sk"], set={"outcome": "submitted", "receipt": found_receipt, "finished_at": now, "reconciled": True},
                       remove=["outcome_pending"]),
                Update(U(uid), a["ledger"], add={"uncertain": -1, "submitted": 1}),
                self._transition(app, "Submitted", {"receipt": found_receipt, "recruitment_stage": "applied", "submitted_at": now}),
                self.event_put(uid, "submission.reconciled", {"reference": found_receipt.get("reference")}, app_id),
                Put({"pk": f"RECEIPT#{found_receipt['reference']}", "sk": "RECEIPT", "user_id": uid, "app_id": app_id}),
                self.outbox_put("notify", {"kind": "submitted", "user_id": uid, "app_id": app_id,
                                           "reference": found_receipt.get("reference")}, f"notify:submitted:{app_id}"),
            ]
        else:
            ops = [
                Update(U(uid), a["sk"], set={"outcome": "unresolved", "finished_at": now}, remove=["outcome_pending"]),
                self._transition(app, "NeedsReview", {"last_error": "submission could not be confirmed; check before retrying"}),
                self.event_put(uid, "submission.unresolved", {}, app_id),
                self.outbox_put("notify", {"kind": "needs_review", "user_id": uid, "app_id": app_id}, f"notify:review:{app_id}:{attempt_id}"),
            ]
        self.store.transact(ops)
        return {"action": "recorded", "state": self.get_app(uid, app_id)["action_state"]}

    # ---- recruitment stage (separate from action state) -----------------------

    def record_stage(self, uid: str, app_id: str, stage: str, evidence: dict, source: str) -> dict:
        if stage not in STAGES:
            raise WorkflowError("bad_stage", stage, 400)
        app = self.get_app(uid, app_id)
        self.store.transact([
            Update(app["pk"], app["sk"], set={"recruitment_stage": stage, "updated_at": self._now_iso(), "version": app["version"] + 1},
                   condition=C("version", "eq", app["version"])),
            self.event_put(uid, f"stage.{stage}", {"evidence": evidence, "source": source}, app_id),
        ])
        return self.get_app(uid, app_id)

    # ---- operations (async command tracking) ---------------------------------

    def start_operation(self, uid: str, kind: str, payload: dict, client_request_id: str, correlation_id: str) -> tuple[dict, bool]:
        """Returns (operation, created). Duplicate client_request_id returns the original."""
        req = self.store.get(U(uid), f"REQ#{client_request_id}")
        if req:
            return self.store.get(U(uid), f"OP#{req['op_id']}") or {}, False
        op_id = new_id("op_")
        now = self._now_iso()
        op = {"pk": U(uid), "sk": f"OP#{op_id}", "entity": "operation", "op_id": op_id, "kind": kind, "status": "accepted",
              "payload": payload, "progress": [], "results": [], "created_at": now, "updated_at": now,
              "correlation_id": correlation_id, "ttl": int(self.clock.now()) + 7 * 86400}
        try:
            self.store.transact([
                Put({"pk": U(uid), "sk": f"REQ#{client_request_id}", "op_id": op_id, "ttl": int(self.clock.now()) + 86400},
                    C("pk", "not_exists")),
                Put(op, C("pk", "not_exists")),
                self.outbox_put("work", {"kind": kind, "user_id": uid, "op_id": op_id, "payload": payload,
                                         "correlation_id": correlation_id}, f"work:op:{op_id}"),
            ])
        except ConditionFailed:
            req = self.store.get(U(uid), f"REQ#{client_request_id}")
            return (self.store.get(U(uid), f"OP#{req['op_id']}") if req else {}) or {}, False
        return op, True

    def op_progress(self, uid: str, op_id: str, *, status: str | None = None, message: str | None = None,
                    result: Any = None, final: dict | None = None) -> None:
        op = self.store.get(U(uid), f"OP#{op_id}")
        if not op:
            return
        sets: dict[str, Any] = {"updated_at": self._now_iso()}
        if status:
            sets["status"] = status
        if message:
            sets["progress"] = (op.get("progress") or [])[-30:] + [{"at": self._now_iso(), "message": message}]
        if result is not None:
            sets["results"] = (op.get("results") or []) + [result]
        if final is not None:
            sets["final"] = final
        self.store.update(Update(U(uid), f"OP#{op_id}", set=sets))

    # ---- usage metering --------------------------------------------------------

    def reserve_usage(self, uid: str, metric: str, amount: int, user_cap: int, global_cap: int) -> bool:
        """Pessimistic reservation of model calls / voice seconds before work starts."""
        date = local_date(self.clock.now(), "UTC")
        try:
            self.store.transact([
                Update(U(uid), f"USAGE#{date}", add={metric: amount}, set={"date": date, "ttl": int(self.clock.now()) + 40 * 86400},
                       condition=Or(C(metric, "not_exists"), C(metric, "le", user_cap - amount))),
                Update("USAGE#GLOBAL", date, add={metric: amount}, set={"ttl": int(self.clock.now()) + 40 * 86400},
                       condition=Or(C(metric, "not_exists"), C(metric, "le", global_cap - amount))),
            ])
            return True
        except ConditionFailed:
            return False

    def usage(self, uid: str) -> dict:
        date = local_date(self.clock.now(), "UTC")
        return self.store.get(U(uid), f"USAGE#{date}") or {}


def packet_preview(packet: dict | None) -> dict | None:
    if not packet:
        return None
    return {"version": packet["version"], "hash": packet["hash"], "body": packet["body"],
            "unknown_required": packet.get("unknown_required", []), "field_evidence": packet.get("field_evidence", {}),
            "fields": packet.get("fields", []),
            "created_at": packet.get("created_at")}


def json_size(obj: Any) -> int:
    return len(canonical_json(obj))
