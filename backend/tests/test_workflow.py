import unittest

from helpers import JOB, P, make, new_app, packet

from career_agent import services, workflow
from career_agent.store import ConditionFailed, TransactionFailed
from career_agent.workflow import WorkflowError


def outbox(store, queue=None):
    return [i for i in store._items.values() if i.get("entity") == "outbox" and (queue is None or i["queue"] == queue)]


class ApplicationCreation(unittest.TestCase):
    def test_duplicate_requisition_is_idempotent(self):
        wf, store, _ = make()
        a = new_app(wf)
        b = new_app(wf)
        self.assertEqual(a["app_id"], b["app_id"])
        self.assertEqual(len(wf.list_apps("u1")), 1)

    def test_cross_user_isolated(self):
        wf, store, _ = make()
        a = new_app(wf, "u1")
        with self.assertRaises(WorkflowError):
            wf.get_app("u2", a["app_id"])
        with self.assertRaises(WorkflowError) as ctx:
            wf.approve(P("u2"), a["app_id"], "x", "dashboard")
        self.assertEqual(ctx.exception.status, 404)


class ReviewMode(unittest.TestCase):
    def test_review_requires_approval_then_queues(self):
        wf, store, _ = make()
        app = new_app(wf)
        app = wf.save_packet("u1", app["app_id"], packet())
        self.assertEqual(app["action_state"], "NeedsApproval")
        self.assertEqual(len(outbox(store, "submit")), 0)
        app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
        self.assertEqual(app["action_state"], "Queued")
        self.assertEqual(len(outbox(store, "submit")), 1)

    def test_duplicate_approval_is_harmless(self):
        wf, store, _ = make()
        app = wf.save_packet("u1", new_app(wf)["app_id"], packet())
        wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
        again = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "telegram")
        self.assertEqual(again["action_state"], "Queued")
        self.assertEqual(len(outbox(store, "submit")), 1)

    def test_stale_approval_rejected(self):
        wf, store, _ = make()
        app = wf.save_packet("u1", new_app(wf)["app_id"], packet())
        old = app["packet_hash"]
        app = wf.save_packet("u1", app["app_id"], packet(cover_note="changed"))
        with self.assertRaises(WorkflowError) as ctx:
            wf.approve(P("u1"), app["app_id"], old, "email")
        self.assertEqual(ctx.exception.code, "stale_packet")

    def test_unknown_required_answers_block(self):
        wf, store, _ = make()
        app = wf.save_packet("u1", new_app(wf)["app_id"], packet(unknown_required=["Are you authorized to work in India?"]))
        self.assertEqual(app["action_state"], "NeedsInformation")
        self.assertEqual(len(outbox(store, "notify")), 1)

    def test_legacy_browser_ready_packet_can_be_explicitly_approved_in_place(self):
        """Old deployed packets could already be Browser ready without approved_hash.

        Clicking Apply in signed-in browser is an explicit approval of that exact
        hash, so the workflow should repair the missing approval without forcing
        an impossible NeedsUserPresence -> NeedsApproval round-trip.
        """
        from career_agent.store import Update

        wf, store, _ = make()
        app = new_app(wf, connector="amazon-jobs")
        local = packet(target={"url": "https://account.amazon.jobs/en-US/applicant/jobs/123/apply",
                               "connector": "amazon-jobs",
                               "submission": {"mode": "local_browser", "can_submit": True,
                                              "requires_user_presence": True}})
        app = wf.save_packet("u1", app["app_id"], local)
        self.assertEqual(app["action_state"], "NeedsApproval")

        # Simulate an application persisted by an older release.
        store.update(Update(app["pk"], app["sk"], set={
            "action_state": "NeedsUserPresence",
            "approved_hash": None,
        }))
        app = wf.get_app("u1", app["app_id"])
        repaired = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "browser_launch")
        self.assertEqual(repaired["action_state"], "NeedsUserPresence")
        self.assertEqual(repaired["approved_hash"], repaired["packet_hash"])
        decision = wf.decide_submission(
            P("u1"), repaired, wf.settings("u1"), reserve_check=True,
            packet=wf.latest_packet("u1", repaired["app_id"]))
        self.assertTrue(decision.allowed)

    def test_authenticated_portal_requires_approval_then_user_presence(self):
        """A live Amazon packet follows the same approval gate as cloud submit,
        then hands execution to the user's signed-in browser."""
        wf, _, _ = make()
        app = new_app(wf, connector="amazon-jobs")
        local = packet(target={"url": "https://www.amazon.jobs/en/jobs/123/sde",
                               "connector": "amazon-jobs",
                               "submission": {"mode": "local_browser", "can_submit": True,
                                              "requires_user_presence": True}})
        app = wf.save_packet("u1", app["app_id"], local)
        self.assertEqual(app["action_state"], "NeedsApproval")
        app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
        self.assertEqual(app["action_state"], "NeedsUserPresence")
        self.assertEqual(len(outbox(wf.store, "submit")), 0)

    def test_local_browser_submission_is_fenced_and_recorded(self):
        wf, store, _ = make()
        app = new_app(wf, connector="amazon-jobs")
        local = packet(target={"url": "https://www.amazon.jobs/en/jobs/123/sde",
                               "connector": "amazon-jobs",
                               "submission": {"mode": "local_browser", "can_submit": True,
                                              "requires_user_presence": True}})
        app = wf.save_packet("u1", app["app_id"], local)
        app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
        app = wf.local_browser_start(P("u1"), app["app_id"], app["packet_hash"])
        self.assertEqual(app["action_state"], "Submitting")
        app = wf.local_browser_dispatch(P("u1"), app["app_id"], app["packet_hash"])
        self.assertTrue(app.get("local_browser_dispatched_at"))
        app = wf.local_browser_complete(P("u1"), app["app_id"], app["packet_hash"], "submitted",
                                        receipt={"reference": "amazon-confirmed"})
        self.assertEqual(app["action_state"], "Submitted")
        self.assertEqual(app["receipt"]["reference"], "amazon-confirmed")

    def test_login_pause_releases_local_browser_capacity(self):
        wf, store, _ = make()
        app = new_app(wf, connector="amazon-jobs")
        local = packet(target={"url": "https://www.amazon.jobs/en/jobs/123/sde",
                               "connector": "amazon-jobs",
                               "submission": {"mode": "local_browser", "can_submit": True,
                                              "requires_user_presence": True}})
        app = wf.save_packet("u1", app["app_id"], local)
        app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
        app = wf.local_browser_start(P("u1"), app["app_id"], app["packet_hash"])
        app = wf.local_browser_complete(P("u1"), app["app_id"], app["packet_hash"], "needs_user",
                                        reason="Please sign in")
        self.assertEqual(app["action_state"], "NeedsUserPresence")
        ledger = store.get("USER#u1", wf.ledger_key("u1", wf.settings("u1")))
        self.assertEqual(ledger["used"], 0)
        self.assertEqual(ledger["reserved"], 0)
        # Login/MFA/question pauses are not submissions. Retrying immediately
        # must not trip the submit cooldown.
        again = wf.local_browser_start(P("u1"), app["app_id"], app["packet_hash"])
        self.assertEqual(again["action_state"], "Submitting")

    def test_local_browser_cooldown_is_checked_only_at_submit_dispatch(self):
        wf, store, _ = make()

        def local_app(key):
            job = dict(__import__("helpers").JOB, job_key=key, canonical_key=key)
            app = wf.create_application("u1", job, {"score": 85, "auto_eligible": True, "blocked": False}, "amazon-jobs")
            local = packet(target={"url": "https://account.amazon.jobs/en-US/applicant/jobs/123/apply",
                                   "connector": "amazon-jobs",
                                   "submission": {"mode": "local_browser", "can_submit": True,
                                                  "requires_user_presence": True}})
            app = wf.save_packet("u1", app["app_id"], local)
            return wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")

        first = local_app("amazon:first")
        first = wf.local_browser_start(P("u1"), first["app_id"], first["packet_hash"])
        first = wf.local_browser_dispatch(P("u1"), first["app_id"], first["packet_hash"])
        wf.local_browser_complete(P("u1"), first["app_id"], first["packet_hash"], "submitted",
                                  receipt={"reference": "amazon-1"})

        second = local_app("amazon:second")
        # Preparing/filling another application is allowed immediately.
        second = wf.local_browser_start(P("u1"), second["app_id"], second["packet_hash"])
        self.assertEqual(second["action_state"], "Submitting")

        # Only the real final write is rate limited.
        with self.assertRaises(WorkflowError) as ctx:
            wf.local_browser_dispatch(P("u1"), second["app_id"], second["packet_hash"])
        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertEqual(wf.get_app("u1", second["app_id"])["action_state"], "NeedsUserPresence")
        ledger = store.get("USER#u1", wf.ledger_key("u1", wf.settings("u1")))
        self.assertEqual(ledger["reserved"], 0)

    def test_manual_handoff_when_this_posting_is_hosted_off_the_board(self):
        """Greenhouse can submit - but only to forms Greenhouse actually hosts.

        Stripe, Databricks and Rubrik embed Greenhouse in their own careers site,
        where the form sits behind their own bot protection. Treating connector
        capability as posting capability would have queued a submission that
        could only fail at the browser.
        """
        wf, _, _ = make()
        app = new_app(wf, connector="greenhouse-public")
        off_board = packet(target={"url": "https://www.rubrik.com/careers/job.751?gh_jid=751",
                                   "connector": "greenhouse-public", "submittable": False})
        app = wf.save_packet("u1", app["app_id"], off_board)
        self.assertEqual(app["action_state"], "ManualHandoff")

    def test_a_greenhouse_hosted_posting_goes_to_approval(self):
        wf, _, _ = make()
        app = new_app(wf, connector="greenhouse-public")
        hosted = packet(target={"url": "https://job-boards.greenhouse.io/twilio/jobs/8177722",
                                "connector": "greenhouse-public", "submittable": True})
        app = wf.save_packet("u1", app["app_id"], hosted)
        self.assertEqual(app["action_state"], "NeedsApproval")


class AutoModes(unittest.TestCase):
    def _auto(self, score, mode="auto_above_80", mandate=True, eligible=True):
        wf, store, clock = make()
        wf.update_settings("u1", {"mode": mode})
        if mandate:
            wf.set_mandate(P("u1"), True, mode)
        app = new_app(wf, score=score, eligible=eligible)
        return wf.save_packet("u1", app["app_id"], packet()), wf, store, clock

    def test_score_80_requires_review(self):
        app, *_ = self._auto(80)
        self.assertEqual(app["action_state"], "NeedsApproval")

    def test_score_81_auto_queues(self):
        app, *_ = self._auto(81)
        self.assertEqual(app["action_state"], "Queued")

    def test_no_mandate_no_auto(self):
        app, *_ = self._auto(95, mandate=False)
        self.assertEqual(app["action_state"], "NeedsApproval")

    def test_revoked_mandate_blocks_at_gate(self):
        app, wf, store, clock = self._auto(90)
        wf.set_mandate(P("u1"), False)
        msg = outbox(store, "submit")[0]["message"]
        res = wf.gate_begin(P("u1"), app["app_id"], msg["attempt_id"], msg["packet_hash"])
        self.assertEqual(res["action"], "denied")
        self.assertEqual(wf.get_app("u1", app["app_id"])["action_state"], "NeedsApproval")

    def test_expired_mandate(self):
        app, wf, store, clock = self._auto(90)
        clock.advance(73 * 3600)
        msg = outbox(store, "submit")[0]["message"]
        self.assertEqual(wf.gate_begin(P("u1"), app["app_id"], msg["attempt_id"], msg["packet_hash"])["action"], "denied")

    def test_auto_eligible_ignores_score_but_not_eligibility(self):
        app, *_ = self._auto(40, mode="auto_eligible")
        self.assertEqual(app["action_state"], "Queued")
        app2, *_ = self._auto(99, mode="auto_eligible", eligible=False)
        self.assertEqual(app2["action_state"], "NeedsApproval")


class Gate(unittest.TestCase):
    def _queued(self, wf, n=1, cap=5):
        wf.update_settings("u1", {"daily_cap": cap, "cooldown_seconds": 30})
        apps = []
        for i in range(n):
            job = dict(JOB, job_key=f"northwind-test-portal:nw-{i}")
            app = wf.create_application("u1", job, {"score": 90, "auto_eligible": True}, "northwind-test-portal")
            app = wf.save_packet("u1", app["app_id"], __import__("helpers").packet())
            app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
            apps.append(app)
        return apps

    def _msg(self, store, app_id):
        return [o["message"] for o in outbox(store, "submit") if o["message"]["app_id"] == app_id][-1]

    def test_happy_path_with_receipt(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        m = self._msg(store, app["app_id"])
        r = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        self.assertEqual(r["action"], "proceed")
        f = r["attempt"]["fencing"]
        self.assertEqual(wf.gate_dispatch("u1", app["app_id"], m["attempt_id"], f, "sig-1")["action"], "submit")
        with self.assertRaises(WorkflowError):
            wf.gate_complete("u1", app["app_id"], m["attempt_id"], "submitted", receipt={})
        wf.gate_complete("u1", app["app_id"], m["attempt_id"], "submitted", receipt={"reference": "NW-123"})
        final = wf.get_app("u1", app["app_id"])
        self.assertEqual(final["action_state"], "Submitted")
        self.assertEqual(final["recruitment_stage"], "applied")

    def test_duplicate_queue_delivery_does_not_double_submit(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        m = self._msg(store, app["app_id"])
        r1 = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        r2 = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        self.assertEqual(r1["action"], "proceed")
        self.assertEqual(r2["action"], "busy")

    def test_lease_expiry_after_dispatch_reconciles_never_resubmits(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        m = self._msg(store, app["app_id"])
        r = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        wf.gate_dispatch("u1", app["app_id"], m["attempt_id"], r["attempt"]["fencing"], "sig-1")
        clock.advance(600)  # worker died after clicking submit
        r2 = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        self.assertEqual(r2["action"], "reconcile")

    def test_worker_crash_before_dispatch_requeues_and_releases(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        m = self._msg(store, app["app_id"])
        wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        clock.advance(600)
        r = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        self.assertEqual(r["action"], "requeued")
        self.assertEqual(wf.get_app("u1", app["app_id"])["action_state"], "Queued")
        ledger = store.get("USER#u1", wf.ledger_key("u1", wf.settings("u1")))
        self.assertEqual(ledger["used"], 0)
        m2 = self._msg(store, app["app_id"])
        self.assertNotEqual(m2["attempt_id"], m["attempt_id"])
        self.assertEqual(wf.gate_begin(P("u1"), app["app_id"], m2["attempt_id"], m2["packet_hash"])["action"], "proceed")

    def test_timeout_after_submit_unknown_then_reconciled(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        m = self._msg(store, app["app_id"])
        r = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        wf.gate_dispatch("u1", app["app_id"], m["attempt_id"], r["attempt"]["fencing"], "sig-1")
        wf.gate_complete("u1", app["app_id"], m["attempt_id"], "unknown", reason="timeout")
        self.assertEqual(wf.get_app("u1", app["app_id"])["action_state"], "OutcomeUnknown")
        ledger = store.get("USER#u1", wf.ledger_key("u1", wf.settings("u1")))
        self.assertEqual(ledger["used"], 1)  # uncertain still consumes capacity
        self.assertEqual(ledger["uncertain"], 1)
        wf.reconcile("u1", app["app_id"], m["attempt_id"], {"reference": "NW-9"})
        self.assertEqual(wf.get_app("u1", app["app_id"])["action_state"], "Submitted")

    def test_unresolved_goes_to_review(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        m = self._msg(store, app["app_id"])
        r = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        wf.gate_dispatch("u1", app["app_id"], m["attempt_id"], r["attempt"]["fencing"], "sig-1")
        wf.gate_complete("u1", app["app_id"], m["attempt_id"], "unknown")
        wf.reconcile("u1", app["app_id"], m["attempt_id"], None)
        self.assertEqual(wf.get_app("u1", app["app_id"])["action_state"], "NeedsReview")

    def test_changed_form_invalidates(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        m = self._msg(store, app["app_id"])
        r = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
        res = wf.gate_dispatch("u1", app["app_id"], m["attempt_id"], r["attempt"]["fencing"], "sig-CHANGED")
        self.assertEqual(res["action"], "abort")
        self.assertEqual(wf.get_app("u1", app["app_id"])["action_state"], "Preparing")
        ledger = store.get("USER#u1", wf.ledger_key("u1", wf.settings("u1")))
        self.assertEqual(ledger["used"], 0)

    def test_daily_cap_race(self):
        wf, store, clock = make()
        apps = self._queued(wf, n=3, cap=2)
        results = []
        for app in apps:
            m = self._msg(store, app["app_id"])
            r = wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])
            results.append(r["action"])
            if r["action"] == "proceed":
                wf.gate_dispatch("u1", app["app_id"], m["attempt_id"], r["attempt"]["fencing"], "sig-1")
                wf.gate_complete("u1", app["app_id"], m["attempt_id"], "submitted", receipt={"reference": "R"})
            clock.advance(31)
        self.assertEqual(results.count("proceed"), 2)
        self.assertEqual(results[2], "denied")

    def test_cooldown_retries_later(self):
        wf, store, clock = make()
        apps = self._queued(wf, n=2)
        m0 = self._msg(store, apps[0]["app_id"])
        r = wf.gate_begin(P("u1"), apps[0]["app_id"], m0["attempt_id"], m0["packet_hash"])
        self.assertEqual(r["action"], "proceed")
        m1 = self._msg(store, apps[1]["app_id"])
        r2 = wf.gate_begin(P("u1"), apps[1]["app_id"], m1["attempt_id"], m1["packet_hash"])
        self.assertEqual(r2["action"], "denied")
        self.assertTrue(r2["retry_later"])
        self.assertEqual(wf.get_app("u1", apps[1]["app_id"])["action_state"], "Queued")

    def test_midnight_uses_new_local_bucket(self):
        wf, store, clock = make()
        apps = self._queued(wf, n=2, cap=1)
        m0 = self._msg(store, apps[0]["app_id"])
        r = wf.gate_begin(P("u1"), apps[0]["app_id"], m0["attempt_id"], m0["packet_hash"])
        wf.gate_dispatch("u1", apps[0]["app_id"], m0["attempt_id"], r["attempt"]["fencing"], "sig-1")
        wf.gate_complete("u1", apps[0]["app_id"], m0["attempt_id"], "submitted", receipt={"reference": "R"})
        clock.advance(86400)
        m1 = self._msg(store, apps[1]["app_id"])
        self.assertEqual(wf.gate_begin(P("u1"), apps[1]["app_id"], m1["attempt_id"], m1["packet_hash"])["action"], "proceed")

    def test_judge_cannot_submit_live(self):
        wf, store, clock = make()
        app = wf.create_application("j1", dict(JOB, job_key="greenhouse-public:1"), {"score": 99, "auto_eligible": True}, "greenhouse-public")
        d = wf.decide_submission(P("j1", is_judge=True), dict(app, approved_hash="h", packet_hash="h"), wf.settings("j1"))
        self.assertFalse(d.allowed)

    def test_pause_before_dispatch(self):
        wf, store, clock = make()
        app = self._queued(wf)[0]
        wf.pause(P("u1"), app["app_id"])
        m = self._msg(store, app["app_id"])
        self.assertEqual(wf.gate_begin(P("u1"), app["app_id"], m["attempt_id"], m["packet_hash"])["action"], "skip")
        wf.resume(P("u1"), app["app_id"])
        m2 = self._msg(store, app["app_id"])
        self.assertNotEqual(m["attempt_id"], m2["attempt_id"])
        self.assertEqual(wf.gate_begin(P("u1"), app["app_id"], m2["attempt_id"], m2["packet_hash"])["action"], "proceed")


class Operations(unittest.TestCase):
    def test_client_request_id_dedup(self):
        wf, store, _ = make()
        op1, c1 = wf.start_operation("u1", "chat", {"text": "hi"}, "req-1", "corr")
        op2, c2 = wf.start_operation("u1", "chat", {"text": "hi"}, "req-1", "corr")
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(op1["op_id"], op2["op_id"])
        self.assertEqual(len(outbox(store, "work")), 1)

    def test_usage_reservation(self):
        wf, _, _ = make()
        self.assertTrue(wf.reserve_usage("u1", "model_calls", 1, 2, 100))
        self.assertTrue(wf.reserve_usage("u1", "model_calls", 1, 2, 100))
        self.assertFalse(wf.reserve_usage("u1", "model_calls", 1, 2, 100))


if __name__ == "__main__":
    unittest.main()


class UsageReservationUnderContention(unittest.TestCase):
    """The two rows reserve_usage writes are the hottest in the table - one per
    user, and USAGE#GLOBAL shared by everyone - and search scores its candidates
    in parallel. DynamoDB answers the collision with TransactionConflict, which
    it documents as retryable and boto3 does not retry by default. Uncaught it
    propagated out of scoring and the job was dropped from the results.
    """

    def _wf(self, outcomes):
        """outcomes: what each successive transact() call does."""
        wf, store, _ = make()
        calls = {"n": 0}
        real = store.transact

        def flaky(ops):
            i = calls["n"]
            calls["n"] += 1
            if i < len(outcomes) and outcomes[i] is not None:
                raise outcomes[i]
            return real(ops)

        store.transact = flaky
        return wf, calls

    def test_a_conflict_is_retried_and_succeeds(self):
        wf, calls = self._wf([TransactionFailed("item[0] TransactionConflict"), None])
        self.assertTrue(wf.reserve_usage("u1", "model_calls", 1, 100, 1000))
        self.assertEqual(calls["n"], 2, "should have retried exactly once")

    def test_it_gives_up_rather_than_retrying_forever(self):
        conflict = TransactionFailed("item[1] TransactionConflict")
        wf, calls = self._wf([conflict] * 10)
        with self.assertRaises(TransactionFailed):
            wf.reserve_usage("u1", "model_calls", 1, 100, 1000)
        self.assertEqual(calls["n"], workflow.USAGE_RESERVE_ATTEMPTS)

    def test_an_exhausted_quota_is_not_retried(self):
        """ConditionFailed is the quota genuinely being spent. Retrying it would
        ask the same question again and bill for the privilege."""
        wf, calls = self._wf([ConditionFailed("cap reached")])
        self.assertFalse(wf.reserve_usage("u1", "model_calls", 1, 100, 1000))
        self.assertEqual(calls["n"], 1, "a refusal must not be retried")

    def test_an_uncontended_reservation_still_takes_one_call(self):
        wf, calls = self._wf([])
        self.assertTrue(wf.reserve_usage("u1", "model_calls", 1, 100, 1000))
        self.assertEqual(calls["n"], 1)


class WatchIntervalFloor(unittest.TestCase):
    """Every enabled watch is a full search, and the worker drains a fixed number
    at a time. Seventy-six watches on a five minute floor arrived faster than they
    could be served and the work queue backed up to 624 messages.
    """

    def test_a_shorter_interval_than_the_floor_is_raised_to_it(self):
        wf, store, _ = make()
        svc_floor = services.WATCH_MIN_INTERVAL_MINUTES
        self.assertEqual(max(svc_floor, min(services.WATCH_MAX_INTERVAL_MINUTES, 5)), svc_floor)

    def test_the_floor_is_fifteen_minutes(self):
        self.assertEqual(services.WATCH_MIN_INTERVAL_MINUTES, 15)

    def test_a_longer_interval_is_respected(self):
        self.assertEqual(
            max(services.WATCH_MIN_INTERVAL_MINUTES, min(services.WATCH_MAX_INTERVAL_MINUTES, 60)), 60)

    def test_a_week_is_the_ceiling(self):
        self.assertEqual(
            max(services.WATCH_MIN_INTERVAL_MINUTES, min(services.WATCH_MAX_INTERVAL_MINUTES, 99999)),
            services.WATCH_MAX_INTERVAL_MINUTES)
