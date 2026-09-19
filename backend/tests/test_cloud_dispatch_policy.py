"""Final cloud-browser dispatch must honor rules changed while the form was filling."""

import pytest
from helpers import P, make, new_app, packet


def begun(*, automatic=False, explicit=False, cap=1):
    wf, store, clock = make()
    wf.update_settings("u1", {"daily_cap": cap})
    if automatic:
        wf.set_mandate(P("u1"), True, "auto_eligible")
    app = wf.save_packet("u1", new_app(wf)["app_id"], packet())
    if not automatic:
        app = wf.approve(P("u1"), app["app_id"], app["packet_hash"], "dashboard")
    if explicit and automatic:
        # Explicit approval persists independently of the automatic mandate.
        from career_agent.store import Update
        store.update(Update(app["pk"], app["sk"], set={"approved_hash": app["packet_hash"]}))
    msg = next(row["message"] for row in store._items.values() if row.get("queue") == "submit")
    result = wf.gate_begin(P("u1"), app["app_id"], msg["attempt_id"], msg["packet_hash"])
    assert result["action"] == "proceed"
    return wf, store, clock, app, msg, result["attempt"]["fencing"]


@pytest.mark.parametrize("change", ["exclude", "revoke", "cap"])
def test_rules_changed_during_cloud_fill_abort_and_release_once(change):
    wf, store, _, app, msg, fence = begun(automatic=change == "revoke")
    if change == "exclude":
        wf.update_settings("u1", {"preferences": {"excluded_companies": ["Northwind Labs"]}})
    elif change == "revoke":
        wf.set_mandate(P("u1"), False)
    else:
        wf.update_settings("u1", {"daily_cap": 0})
    result = wf.gate_dispatch("u1", app["app_id"], msg["attempt_id"], fence, "sig-1")
    assert result["action"] == "abort"
    assert result["reason"] == "submission_policy_changed"
    attempt = wf._attempt("u1", app["app_id"], msg["attempt_id"])
    assert not attempt.get("dispatched_at")
    assert attempt["outcome"] == "denied_before_dispatch"
    assert wf.get_app("u1", app["app_id"])["action_state"] == "KnownFailure"
    assert wf.gate_dispatch("u1", app["app_id"], msg["attempt_id"], fence, "sig-1")["action"] == "abort"
    ledger = store.get("USER#u1", attempt["ledger"])
    assert ledger["used"] == ledger["reserved"] == 0


def test_cloud_final_gate_uses_own_slot_and_does_not_block_its_own_cooldown():
    wf, store, _, app, msg, fence = begun(cap=1)
    assert wf.gate_dispatch("u1", app["app_id"], msg["attempt_id"], fence, "sig-1")["action"] == "submit"
    result = wf.gate_dispatch("u1", app["app_id"], msg["attempt_id"], fence, "sig-1")
    assert result == {"action": "abort", "reason": "lease lost or already dispatched"}
    attempt = wf._attempt("u1", app["app_id"], msg["attempt_id"])
    assert store.get("USER#u1", attempt["ledger"])["used"] == 1


def test_explicit_review_remains_authorized_after_unrelated_mandate_revocation():
    wf, _, _, app, msg, fence = begun(automatic=True, explicit=True)
    wf.set_mandate(P("u1"), False)
    assert wf.gate_dispatch("u1", app["app_id"], msg["attempt_id"], fence, "sig-1")["action"] == "submit"
