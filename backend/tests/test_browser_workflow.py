"""Regression coverage for retries, approvals and the authenticated browser write boundary."""

import pytest
from helpers import P, make, new_app, packet

from career_agent.store import Update
from career_agent.workflow import WorkflowError


def ready(wf, *, auto=False):
    if auto:
        wf.set_mandate(P("u1"), True, "auto_eligible", scope={"connectors": ["amazon-jobs"]})
    app = new_app(wf, connector="amazon-jobs")
    data = packet(target={"url": "https://account.amazon.jobs/en-US/applicant/jobs/123/apply",
                          "connector": "amazon-jobs",
                          "submission": {"mode": "local_browser", "can_submit": True}})
    app = wf.save_packet("u1", app["app_id"], data)
    if not auto:
        app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
    return app, data


def start(wf, app, session="session-one"):
    return wf.local_browser_start(P("u1"), app["app_id"], app["packet_hash"], session_id=session)


def dispatch(wf, app, session="session-one"):
    return wf.local_browser_dispatch(P("u1"), app["app_id"], app["packet_hash"], session_id=session)


def complete(wf, app, outcome, session="session-one", **kwargs):
    return wf.local_browser_complete(P("u1"), app["app_id"], app["packet_hash"], outcome,
                                     session_id=session, **kwargs)


def ledger(wf, store):
    return store.get("USER#u1", wf.ledger_key("u1", wf.settings("u1")))


def test_reprepare_identical_content_can_be_approved_again():
    wf, _, _ = make()
    app, data = ready(wf)
    old_hash = app["packet_hash"]
    app = wf.save_packet("u1", app["app_id"], data)
    assert app["packet_hash"] == old_hash
    assert app["approved_hash"] is None
    app = wf.approve(P("u1"), app["app_id"], old_hash, "dashboard")
    assert app["action_state"] == "NeedsUserPresence"
    assert app["approved_hash"] == old_hash


def test_browser_profile_records_are_covered_by_packet_approval():
    wf, _, _ = make()
    app, data = ready(wf)
    approved_hash = app["packet_hash"]
    data["profile_records"] = {"experience": [{"title": "Engineer", "company": "Example"}], "education": []}
    app = wf.save_packet("u1", app["app_id"], data)
    assert app["packet_hash"] != approved_hash
    assert wf.latest_packet("u1", app["app_id"])["body"]["profile_records"] == data["profile_records"]
    with pytest.raises(WorkflowError) as error:
        wf.approve(P("u1"), app["app_id"], approved_hash, "dashboard")
    assert error.value.code == "stale_packet"


def test_dispatch_can_use_its_own_last_reserved_daily_slot():
    wf, store, _ = make()
    wf.update_settings("u1", {"daily_cap": 1})
    app, _ = ready(wf)
    app = start(wf, app)
    assert ledger(wf, store)["used"] == 1
    assert dispatch(wf, app)["local_browser_dispatched_at"]


def test_repeated_start_and_completion_do_not_double_charge_capacity():
    wf, store, _ = make()
    app, _ = ready(wf)
    app = start(wf, app)
    assert start(wf, app)["current_attempt"] == app["current_attempt"]
    assert ledger(wf, store)["used"] == 1
    complete(wf, app, "needs_user", reason="Sign in")
    complete(wf, app, "needs_user", reason="Sign in")
    assert ledger(wf, store)["used"] == ledger(wf, store)["reserved"] == 0


def test_duplicate_dispatch_never_grants_a_second_submit_click():
    wf, store, _ = make()
    app, _ = ready(wf)
    app = dispatch(wf, start(wf, app))
    with pytest.raises(WorkflowError) as error:
        dispatch(wf, app)
    assert error.value.code == "already_dispatched"
    assert ledger(wf, store)["used"] == 1


def test_revoked_mandate_before_dispatch_releases_reservation():
    wf, store, _ = make()
    app, _ = ready(wf, auto=True)
    app = start(wf, app)
    wf.set_mandate(P("u1"), False)
    with pytest.raises(WorkflowError) as error:
        dispatch(wf, app)
    assert error.value.code == "submission_blocked"
    assert wf.get_app("u1", app["app_id"])["action_state"] == "NeedsUserPresence"
    assert ledger(wf, store)["used"] == 0


def test_reduced_cap_before_dispatch_releases_reservation():
    wf, store, _ = make()
    app, _ = ready(wf)
    app = start(wf, app)
    wf.update_settings("u1", {"daily_cap": 0})
    with pytest.raises(WorkflowError) as error:
        dispatch(wf, app)
    assert error.value.code == "submission_blocked"
    assert ledger(wf, store)["used"] == 0


def test_excluded_company_changed_during_filling_blocks_both_runner_and_dispatch():
    wf, store, _ = make()
    app, _ = ready(wf)
    app = start(wf, app)
    wf.update_settings("u1", {"preferences": {"excluded_companies": ["Northwind Labs"]}})
    decision = wf.decide_submission(P("u1"), app, wf.settings("u1"), reserve_check=True,
                                    packet=wf.latest_packet("u1", app["app_id"]), local_reservation=True)
    assert not decision.allowed
    assert "forbid-current-preferences" in decision.reasons
    with pytest.raises(WorkflowError) as error:
        dispatch(wf, app)
    assert error.value.code == "submission_blocked"
    assert not wf.get_app("u1", app["app_id"]).get("local_browser_dispatched_at")
    assert ledger(wf, store)["used"] == 0


def test_current_location_uses_aliases_but_known_mismatch_blocks():
    wf, _, _ = make()
    app, _ = ready(wf)
    wf.update_settings("u1", {"preferences": {"locations": ["Bangalore"]}})
    assert start(wf, app)["action_state"] == "Submitting"  # job uses Bengaluru
    wf.update_settings("u1", {"preferences": {"locations": ["London"]}})
    with pytest.raises(WorkflowError) as error:
        dispatch(wf, app)
    assert error.value.code == "submission_blocked"


def test_unknown_location_and_work_mode_do_not_override_exact_user_review():
    wf, store, _ = make()
    app, _ = ready(wf)
    store.update(Update(app["pk"], app["sk"], set={"location": None}))
    wf.update_settings("u1", {"preferences": {"locations": ["Bangalore"], "work_modes": ["remote"]}})
    assert start(wf, app)["action_state"] == "Submitting"


def test_reopened_browser_rejects_old_session_completion():
    wf, store, _ = make()
    app, _ = ready(wf)
    app = start(wf, app)
    wf.local_browser_reopen(P("u1"), app["app_id"], app["packet_hash"])
    app = start(wf, app, "session-two")
    with pytest.raises(WorkflowError) as error:
        complete(wf, app, "needs_user", session="session-one")
    assert error.value.code == "stale_session"
    assert ledger(wf, store)["reserved"] == 1
    assert dispatch(wf, app, "session-two")["local_browser_dispatched_at"]


def test_replaced_capability_cannot_start_before_replacement_tab_starts():
    wf, store, _ = make()
    app, _ = ready(wf)
    store.update(Update(app["pk"], app["sk"], set={"browser_session_id": "session-two"}))
    with pytest.raises(WorkflowError) as error:
        start(wf, app, "session-one")
    assert error.value.code == "stale_session"
    assert start(wf, app, "session-two")["action_state"] == "Submitting"


def test_reopen_after_dispatch_is_rejected():
    wf, _, _ = make()
    app, _ = ready(wf)
    app = dispatch(wf, start(wf, app))
    with pytest.raises(WorkflowError) as error:
        wf.local_browser_reopen(P("u1"), app["app_id"], app["packet_hash"])
    assert error.value.code == "already_dispatched"


def test_failed_attempt_marker_does_not_contaminate_reprepared_run():
    wf, store, clock = make()
    app, data = ready(wf)
    app = dispatch(wf, start(wf, app))
    complete(wf, app, "known_failure", reason="Employer rejected a required answer")
    app = wf.save_packet("u1", app["app_id"], data)
    app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
    clock.advance(121)
    app = start(wf, app, "session-two")
    assert not app.get("local_browser_dispatched_at")
    complete(wf, app, "needs_user", session="session-two", reason="Needs answer")
    assert ledger(wf, store)["used"] == 1  # only the previous actual attempt
    assert ledger(wf, store)["reserved"] == 0


def test_success_needs_a_recorded_dispatch():
    wf, store, _ = make()
    app, _ = ready(wf)
    app = start(wf, app)
    with pytest.raises(WorkflowError) as error:
        complete(wf, app, "submitted", receipt={"reference": "R-1"})
    assert error.value.code == "not_dispatched"
    assert ledger(wf, store)["reserved"] == 1


def test_late_receipt_reconciles_unknown_once_without_another_write():
    wf, store, _ = make()
    app, _ = ready(wf)
    app = dispatch(wf, start(wf, app))
    complete(wf, app, "unknown", reason="Confirmation still loading")
    complete(wf, app, "unknown")
    assert ledger(wf, store)["uncertain"] == 1
    final = complete(wf, app, "submitted", receipt={"reference": "R-1"})
    assert final["action_state"] == "Submitted"
    complete(wf, app, "submitted", receipt={"reference": "R-1"})
    assert ledger(wf, store)["uncertain"] == 0
    assert ledger(wf, store)["submitted"] == ledger(wf, store)["used"] == 1
