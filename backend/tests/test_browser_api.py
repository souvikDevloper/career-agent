import json

import pytest
from test_prepare_flow import UID, make_services, save_job

from career_agent import applying
from career_agent.handlers import api
from career_agent.store import Update
from career_agent.workflow import Principal, WorkflowError


def event(body=None):
    return {"body": json.dumps(body or {})}


@pytest.fixture
def browser(monkeypatch):
    svc, _ = make_services()
    job = save_job(svc)
    monkeypatch.setattr(applying, "draft_cover_note", lambda *a, **k: None)
    monkeypatch.setattr(api, "_svc", lambda: svc)
    app = svc.request_prepare(UID, job_key=job["job_key"], apply_after_prepare=True)
    app = svc.prepare(UID, app["app_id"])
    return svc, app


def launch(app):
    response = api.browser_session_create(event({"packet_hash": app["packet_hash"]}), Principal(UID), "test", app["app_id"])
    return json.loads(response["body"])["token"]


def test_reopening_interrupted_form_invalidates_old_token_and_releases_quota(browser):
    svc, app = browser
    old = launch(app)
    api.browser_session_start(event(), None, "test", old)
    new = launch(app)
    with pytest.raises(WorkflowError, match="another browser session"):
        api.browser_session_start(event(), None, "test", old)
    api.browser_session_start(event(), None, "test", new)
    ledger = svc.store.get(f"USER#{UID}", svc.wf.ledger_key(UID, svc.wf.settings(UID)))
    assert ledger["used"] == ledger["reserved"] == 1


def test_resolver_pins_resume_facts_to_approved_packet_and_preserves_control_ids(browser):
    svc, app = browser
    token = launch(app)
    svc.profiles.correct(UID, {"name": "New Name"})
    response = api.browser_session_resolve_questions(event({"questions": [
        {"id": "given-name", "label": "Given Name(s)", "required": True}
    ]}), None, "test", token)
    answers = json.loads(response["body"])["answers"]
    assert answers == [{"id": "given-name", "label": "Given Name(s)", "value": "Asha", "source": "resume:name"}]


def test_long_saved_question_round_trips_and_duplicate_save_is_idempotent(browser):
    svc, app = browser
    token = launch(app)
    api.browser_session_start(event(), None, "test", token)
    label = "Have you ever worked in a role with responsibility for production software development and deployment " + "outside of an internship?"
    body = event({"answers": {label: "No"}})
    api.browser_session_answers(body, None, "test", token)
    version = svc.profiles.current(UID)["version"]
    api.browser_session_answers(body, None, "test", token)
    assert svc.profiles.current(UID)["version"] == version
    response = api.browser_session_resolve_questions(event({"questions": [
        {"label": label, "options": ["Yes", "No"]}
    ]}), None, "test", token)
    assert json.loads(response["body"])["answers"][0]["value"] == "No"


def test_new_session_cannot_be_launched_after_dispatch(browser):
    svc, app = browser
    token = launch(app)
    api.browser_session_start(event(), None, "test", token)
    api.browser_session_dispatch(event(), None, "test", token)
    with pytest.raises(WorkflowError, match="not ready"):
        launch(app)
    with pytest.raises(WorkflowError, match="already|dispatched|submitted"):
        api.browser_session_dispatch(event(), None, "test", token)


def test_authenticated_user_can_reconcile_after_browser_token_expires(browser):
    svc, app = browser
    token = launch(app)
    api.browser_session_start(event(), None, "test", token)
    api.browser_session_dispatch(event(), None, "test", token)
    response = api.handoff_complete(event(), Principal(UID), "test", app["app_id"])
    result = json.loads(response["body"])["application"]
    assert result["action_state"] == "Submitted"
    assert result["receipt"]["user_reported"] is True
    ledger = svc.store.get(f"USER#{UID}", svc.wf.ledger_key(UID, svc.wf.settings(UID)))
    assert ledger["reserved"] == 0
    assert ledger["submitted"] == 1


def connect_runner():
    response = api.browser_runner_connect(event(), Principal(UID), "test")
    return json.loads(response["body"])["token"]


def next_application(token):
    return json.loads(api.browser_runner_next(event(), None, "test", token)["body"])


def test_runner_launches_approved_job_once_and_respects_disconnect(browser):
    _, app = browser
    token = connect_runner()
    first = next_application(token)
    assert first["application"]["app_id"] == app["app_id"]
    assert next_application(token)["application"] is None
    api.browser_runner_disconnect(event(), Principal(UID), "test")
    with pytest.raises(WorkflowError, match="disconnected"):
        next_application(token)


def test_runner_cannot_approve_an_unapproved_review_packet(browser):
    svc, app = browser
    svc.store.update(Update(app["pk"], app["sk"], set={"approved_hash": None}))
    assert next_application(connect_runner())["application"] is None
    assert svc.wf.get_app(UID, app["app_id"])["approved_hash"] is None


def test_runner_uses_mandate_without_turning_it_into_permanent_approval(browser):
    svc, app = browser
    svc.store.update(Update(app["pk"], app["sk"], set={"approved_hash": None}))
    svc.wf.set_mandate(Principal(UID), True, "auto_above_80", scope={"connectors": ["workday-public"]})
    next_app = next_application(connect_runner())["application"]
    assert next_app["app_id"] == app["app_id"]
    assert svc.wf.get_app(UID, app["app_id"])["approved_hash"] is None
    svc.wf.set_mandate(Principal(UID), False)
    with pytest.raises(WorkflowError, match="approved|policy"):
        api.browser_session_start(event(), None, "test", next_app["token"])


def test_pairing_replacement_invalidates_old_runner(browser):
    old = connect_runner()
    new = connect_runner()
    with pytest.raises(WorkflowError, match="disconnected"):
        next_application(old)
    assert next_application(new)["application"] is not None


def test_expired_predispatch_runner_releases_capacity_and_queue(browser):
    svc, app = browser
    runner = connect_runner()
    next_app = next_application(runner)["application"]
    api.browser_session_start(event(), None, "test", next_app["token"])
    svc.store.update(Update(f"USER#{UID}", "BROWSER_RUNNER", set={"launch_until": 0}))
    result = next_application(runner)
    assert result["application"] is None
    assert result["reason"] != "current_application_in_progress"
    assert svc.wf.get_app(UID, app["app_id"])["action_state"] == "NeedsUserPresence"
    ledger = svc.store.get(f"USER#{UID}", svc.wf.ledger_key(UID, svc.wf.settings(UID)))
    assert ledger["used"] == ledger["reserved"] == 0


def test_disconnect_revokes_pending_session_and_releases_reservation(browser):
    svc, _ = browser
    next_app = next_application(connect_runner())["application"]
    api.browser_session_start(event(), None, "test", next_app["token"])
    api.browser_runner_disconnect(event(), Principal(UID), "test")
    with pytest.raises(WorkflowError, match="disconnected"):
        api.browser_session_dispatch(event(), None, "test", next_app["token"])
    ledger = svc.store.get(f"USER#{UID}", svc.wf.ledger_key(UID, svc.wf.settings(UID)))
    assert ledger["used"] == ledger["reserved"] == 0
