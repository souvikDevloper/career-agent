"""Offline tests for scheduled discovery -> preparation -> approval policy -> notifications."""

import pytest
from test_prepare_flow import UID, make_services, save_job

from career_agent import applying, discovery
from career_agent.notify import compose
from career_agent.store import Update
from career_agent.workflow import Principal


def outbox(store, kind):
    return [row for row in store._items.values() if row.get("entity") == "outbox" and row.get("message", {}).get("kind") == kind]


@pytest.fixture
def watch_env(monkeypatch):
    svc, store = make_services()
    job = save_job(svc)
    monkeypatch.setattr(discovery, "all_sources", lambda: [job["feed"]])
    monkeypatch.setattr(discovery, "poll", lambda *args, **kwargs: {"source": job["feed"], "new": [], "changed": []})
    monkeypatch.setattr(applying, "draft_cover_note", lambda *args, **kwargs: None)
    return svc, store, job


def test_watch_initial_check_uses_existing_feed_cache_and_unchanged_results_are_deduplicated(watch_env):
    svc, store, job = watch_env
    watch = svc.create_watch(UID, "software", 30)
    assert len(outbox(store, "check_watch")) == 1
    first = svc.check_watch(UID, watch["watch_id"])
    second = svc.check_watch(UID, watch["watch_id"])
    assert first["queued"] == 1  # feed=workday:adobe..., source=workday-public
    assert second["queued"] == 0
    assert outbox(store, "match_new_job")[0]["message"]["job_key"] == job["job_key"]


def test_custom_watch_interval_is_persisted_and_obeyed(watch_env):
    svc, store, _ = watch_env
    watch = svc.create_watch(UID, "software", 30)
    svc.run_monitor()
    assert len(outbox(store, "check_watch")) == 1
    svc.wf.clock.advance(29 * 60)
    svc.run_monitor()
    assert len(outbox(store, "check_watch")) == 1
    svc.wf.clock.advance(60)
    svc.run_monitor()
    svc.run_monitor()
    assert len(outbox(store, "check_watch")) == 2
    updated = svc.update_watch(UID, watch["watch_id"], interval_minutes=120)
    assert updated["interval_minutes"] == 120
    svc.run_monitor()
    assert store.get(updated["pk"], updated["sk"])["next_check_at"] == svc.wf.clock.now() + 7200


def test_named_watch_queries_direct_employer_and_source_failure_cannot_trigger_auto_apply(watch_env, monkeypatch):
    svc, store, _ = watch_env
    watch = svc.create_watch(UID, "google swe", 15, company="Google", role="early career swe", location="India")
    calls = []

    def unavailable(wf, **kwargs):
        calls.append(kwargs)
        kwargs["stats"].update({"successful_sources": [], "failed_sources": [{"source": "google:direct"}]})
        return []

    monkeypatch.setattr(discovery, "live_search", unavailable)
    assert svc.check_watch(UID, watch["watch_id"])["status"] == "source_unavailable"
    assert calls[0]["company"] == "Google"
    assert calls[0]["role"] == "early career swe"
    assert not outbox(store, "match_new_job")


@pytest.mark.parametrize("mode,score,expected", [
    ("review", 95, "NeedsApproval"),
    ("auto_above_80", 80, "NeedsApproval"),
    ("auto_above_80", 81, "NeedsUserPresence"),
    ("auto_eligible", 40, "NeedsUserPresence"),
])
def test_watch_prepares_then_obeys_real_review_or_automatic_rules(watch_env, monkeypatch, mode, score, expected):
    svc, store, job = watch_env
    watch = svc.create_watch(UID, "software", 30)
    if mode != "review":
        svc.wf.set_mandate(Principal(UID), True, mode)
    match = {"score": score, "auto_eligible": True, "blocked": False, "filters": []}
    monkeypatch.setattr(svc.matcher, "match", lambda *args, **kwargs: match)
    svc.match_new_job(UID, job["job_key"], watch["watch_id"])
    app = svc.wf.list_apps(UID)[0]
    assert app["action_state"] == "Preparing"
    assert len(outbox(store, "new_match")) == len(outbox(store, "preparing")) == 1
    app = svc.prepare(UID, app["app_id"], prepare_request_id=app["prepare_request_id"])
    assert app["action_state"] == expected
    version = app["packet_version"]
    svc.match_new_job(UID, job["job_key"], watch["watch_id"])
    assert svc.wf.get_app(UID, app["app_id"])["packet_version"] == version
    assert len(outbox(store, "prepare")) == 1


def test_deleted_watch_queued_match_does_not_prepare(watch_env):
    svc, store, job = watch_env
    watch = svc.create_watch(UID, "software", 30)
    svc.delete_watch(UID, watch["watch_id"])
    assert svc.match_new_job(UID, job["job_key"], watch["watch_id"]) is None
    assert not outbox(store, "prepare")


def test_live_browser_success_queues_submitted_notification(watch_env):
    svc, store, job = watch_env
    app = svc.request_prepare(UID, job_key=job["job_key"], apply_after_prepare=True)
    app = svc.prepare(UID, app["app_id"])
    principal = Principal(UID)
    app = svc.wf.local_browser_start(principal, app["app_id"], app["packet_hash"])
    svc.wf.local_browser_dispatch(principal, app["app_id"], app["packet_hash"])
    svc.wf.local_browser_complete(principal, app["app_id"], app["packet_hash"], "submitted", receipt={"reference": "R-1"})
    svc.wf.local_browser_complete(principal, app["app_id"], app["packet_hash"], "submitted", receipt={"reference": "R-1"})
    assert len(outbox(store, "submitted")) == 1
    subject, body, _ = compose({"kind": "preparing"}, app)
    assert "Preparing" in subject and "verified answers" in body


def test_judge_default_mandate_never_includes_live_connectors(watch_env):
    svc, _, _ = watch_env
    settings = svc.wf.set_mandate(Principal(UID, is_judge=True), True, "auto_eligible")
    assert settings["mandate"]["scope"]["connectors"] == ["northwind-test-portal"]


def test_preference_and_watch_changes_rescore_unchanged_posting(watch_env):
    svc, store, _ = watch_env
    watch = svc.create_watch(UID, "software", 30)
    assert svc.check_watch(UID, watch["watch_id"])["queued"] == 1
    svc.wf.update_settings(UID, {"preferences": {"roles": ["software"]}})
    assert svc.check_watch(UID, watch["watch_id"])["queued"] == 1
    assert svc.check_watch(UID, watch["watch_id"])["queued"] == 0
    svc.update_watch(UID, watch["watch_id"], role="software")
    assert svc.check_watch(UID, watch["watch_id"])["queued"] == 1
    assert len(outbox(store, "match_new_job")) == 3


def test_old_queued_watch_revision_cannot_create_wrong_company_application(watch_env, monkeypatch):
    svc, store, job = watch_env
    watch = svc.create_watch(UID, "software", 30)
    svc.check_watch(UID, watch["watch_id"])
    message = outbox(store, "match_new_job")[0]["message"]
    svc.update_watch(UID, watch["watch_id"], company="Google")
    monkeypatch.setattr(svc.matcher, "match", lambda *args, **kwargs: pytest.fail("stale criteria reached the model"))
    assert svc.match_new_job(UID, job["job_key"], watch["watch_id"], watch_revision=message["watch_revision"]) is None
    # Legacy queue messages also recheck the current filters.
    assert svc.match_new_job(UID, job["job_key"], watch["watch_id"]) is None
    assert svc.wf.list_apps(UID) == []


def test_watch_edit_during_scoring_discards_old_match(watch_env, monkeypatch):
    svc, _, job = watch_env
    watch = svc.create_watch(UID, "software", 30)

    def score_then_edit(*args, **kwargs):
        svc.update_watch(UID, watch["watch_id"], company="Google")
        return {"score": 95, "auto_eligible": True, "blocked": False, "filters": []}

    monkeypatch.setattr(svc.matcher, "match", score_then_edit)
    assert svc.match_new_job(UID, job["job_key"], watch["watch_id"], watch_revision=watch["revision"]) is None
    assert svc.wf.list_apps(UID) == []


def test_eligible_rematch_recovers_ineligible_app_with_current_score(watch_env, monkeypatch):
    svc, store, job = watch_env
    watch = svc.create_watch(UID, "software", 30)
    app = svc.wf.create_application(UID, job, {"score": 25, "auto_eligible": False, "blocked": True}, "workday-public")
    store.update(Update(app["pk"], app["sk"], set={"action_state": "Ineligible"}))
    monkeypatch.setattr(svc.matcher, "match", lambda *args, **kwargs: {
        "score": 91, "auto_eligible": True, "blocked": False, "filters": []})
    svc.match_new_job(UID, job["job_key"], watch["watch_id"])
    current = svc.wf.get_app(UID, app["app_id"])
    assert current["action_state"] == "Preparing"
    assert current["score"] == 91 and current["auto_eligible"] and not current["blocked"]


@pytest.mark.parametrize("state", ["Submitting", "Submitted", "OutcomeUnknown", "Withdrawn"])
def test_rematch_does_not_mutate_active_or_final_application(watch_env, monkeypatch, state):
    svc, store, job = watch_env
    watch = svc.create_watch(UID, "software", 30)
    app = svc.wf.create_application(UID, job, {"score": 91, "auto_eligible": True, "blocked": False}, "workday-public")
    store.update(Update(app["pk"], app["sk"], set={"action_state": state}))
    before = svc.wf.get_app(UID, app["app_id"])
    monkeypatch.setattr(svc.matcher, "match", lambda *args, **kwargs: {
        "score": 25, "auto_eligible": False, "blocked": True, "filters": []})
    svc.match_new_job(UID, job["job_key"], watch["watch_id"])
    assert svc.wf.get_app(UID, app["app_id"]) == before
    assert not outbox(store, "prepare")


def test_astra_watch_work_uses_dedicated_queue(watch_env):
    svc, store, _ = watch_env
    watch = svc.create_watch(UID, "software", 30)
    created = outbox(store, "check_watch")
    assert created and created[-1]["queue"] == "watch"

    assert svc.check_watch(UID, watch["watch_id"])["queued"] == 1
    matches = outbox(store, "match_new_job")
    assert matches and matches[-1]["queue"] == "watch"


def test_manual_monitor_only_fans_out_requesting_users_watches(watch_env):
    svc, store, _ = watch_env
    svc.create_watch(UID, "software", 30)
    svc.create_watch("other-user", "software", 30)
    before = set(store._items)

    summary = svc.run_monitor(force=True, user_id=UID)

    created = [
        row for key, row in store._items.items()
        if key not in before and row.get("entity") == "outbox"
        and row.get("message", {}).get("kind") == "check_watch"
    ]
    assert summary["fanout"] == 1
    assert len(created) == 1
    assert created[0]["queue"] == "watch"
    assert created[0]["message"]["user_id"] == UID


def test_monitor_fanout_is_bounded_per_scheduler_run(watch_env):
    svc, store, _ = watch_env
    for n in range(12):
        svc.create_watch(UID, f"software {n}", 30)
    before = set(store._items)

    summary = svc.run_monitor(force=True)

    created = [
        row for key, row in store._items.items()
        if key not in before and row.get("entity") == "outbox"
        and row.get("message", {}).get("kind") == "check_watch"
    ]
    assert summary["fanout"] == 10
    assert len(created) == 10
