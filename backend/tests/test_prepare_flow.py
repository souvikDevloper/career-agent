import helpers  # noqa: F401

from career_agent import applying, policy
from career_agent.sources import greenhouse
from career_agent.matching import save_job_snapshot
from career_agent.services import Services
from career_agent.store import MemoryStore
from career_agent.util import FixedClock


UID = "u1"


def make_services():
    policy.set_engine(policy.ReferenceEngine())
    store = MemoryStore()
    svc = Services(store, FixedClock(helpers.T0))
    facts = {
        "name": "Asha Rao",
        "email": "asha@example.test",
        "phone": "+91 9999999999",
        "links": {},
        "education": [{"school": "IIEST", "degree": "B.Tech", "field": "Computer Science",
                       "graduation_year": 2027, "evidence": "B.Tech Computer Science 2027", "verified": True}],
        "experience": [],
        "projects": [],
        "skills": [{"name": "Python", "evidence": "Python", "verified": True}],
        "work_authorization": {"value": None, "verified": False},
    }
    svc.profiles.save_version(UID, facts, "resumes/u1/resume.pdf", "Asha Rao Python", "test")
    return svc, store


def save_job(svc, key="workday:adobe:123"):
    job = {
        "job_key": key,
        "canonical_key": key,
        "source": "workday-public",
        "feed": "workday:adobe:wd5:external_experienced",
        "connector": "workday-public",
        "external_id": "123",
        "company": "Adobe",
        "title": "Software Engineer",
        "location": "Bengaluru",
        "url": "https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/123",
        "apply": {"kind": "external", "url": "https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/123"},
        "description": "Build software systems.",
        "content_hash": "jobhash",
        "environment": "live",
    }
    save_job_snapshot(svc.wf, job)
    svc.store.put({
        "pk": f"USER#{UID}", "sk": f"MATCH#{key}", "entity": "match", "job_key": key,
        "score": 82, "auto_eligible": True, "blocked": False,
    })
    return job


def test_explicit_prepare_can_be_requested_again_without_old_outbox_collision():
    svc, store = make_services()
    job = save_job(svc)

    first = svc.request_prepare(UID, job_key=job["job_key"], apply_after_prepare=True)
    assert first["action_state"] == "Preparing"
    second = svc.request_prepare(UID, app_id=first["app_id"], apply_after_prepare=True)
    assert second["action_state"] == "Preparing"

    outbox = [x for x in store._items.values()
              if x.get("entity") == "outbox" and (x.get("message") or {}).get("kind") == "prepare"]
    assert len(outbox) == 2
    assert len({x["pk"] for x in outbox}) == 2


def test_prepare_and_apply_approves_completed_local_browser_packet(monkeypatch):
    svc, _ = make_services()
    job = save_job(svc)
    monkeypatch.setattr(applying, "draft_cover_note", lambda *a, **k: None)

    app = svc.request_prepare(UID, job_key=job["job_key"], apply_after_prepare=True)
    app = svc.prepare(UID, app["app_id"])

    assert app["action_state"] == "NeedsUserPresence"
    assert app["approved_hash"] == app["packet_hash"]
    assert app["apply_after_prepare"] is False


def test_stripe_external_greenhouse_prepare_asks_once_then_continues(monkeypatch):
    svc, _ = make_services()
    key = "greenhouse:stripe:8172487"
    job = {
        "job_key": key,
        "canonical_key": key,
        "source": "greenhouse-public",
        "feed": "greenhouse:stripe",
        "connector": "greenhouse-public",
        "board": "stripe",
        "external_id": "8172487",
        "company": "Stripe",
        "title": "Software Engineer, Intern",
        "location": "Bengaluru, India",
        "url": "https://stripe.com/jobs/search?gh_jid=8172487",
        "apply": {"kind": "external", "url": "https://stripe.com/jobs/search?gh_jid=8172487"},
        "description": "Build production software.",
        "content_hash": "stripehash",
        "environment": "live",
    }
    save_job_snapshot(svc.wf, job)
    svc.store.put({
        "pk": f"USER#{UID}", "sk": f"MATCH#{key}", "entity": "match", "job_key": key,
        "score": 76, "auto_eligible": True, "blocked": False,
    })

    monkeypatch.setattr(applying, "draft_cover_note", lambda *a, **k: None)
    monkeypatch.setattr(greenhouse, "read_form", lambda board, job_id: {
        "signature": "stripe-form-v1",
        "action": None,
        "fields": [
            {"name": "email", "label": "Email", "type": "text", "required": True, "options": []},
            {"name": "question_1", "label": "Will you now or in the future require visa sponsorship?",
             "type": "select", "required": True,
             "options": [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}]},
        ],
    })

    app = svc.request_prepare(UID, job_key=key, apply_after_prepare=True)
    assert app["action_state"] == "Preparing"

    app = svc.prepare(UID, app["app_id"])
    assert app["action_state"] == "NeedsInformation"
    assert app["apply_after_prepare"] is True

    svc.profiles.save_answers(UID, {"Will you now or in the future require visa sponsorship?": "No"})
    app = svc.request_prepare(UID, app_id=app["app_id"])
    app = svc.prepare(UID, app["app_id"])

    assert app["action_state"] == "NeedsUserPresence"
    assert app["approved_hash"] == app["packet_hash"]
    assert app["apply_after_prepare"] is False


def test_stale_stripe_placeholder_canonical_key_is_repaired_before_application_creation():
    svc, store = make_services()
    key = "greenhouse:stripe:9001"
    job = {
        "job_key": key,
        # Simulates a row persisted by the old Stripe bug.
        "canonical_key": "greenhouse:stripe:See Opening ID",
        "source": "greenhouse-public",
        "feed": "greenhouse:stripe",
        "connector": "greenhouse-public",
        "board": "stripe",
        "external_id": "9001",
        "company": "Stripe",
        "title": "Software Engineer",
        "location": "Bengaluru",
        "url": "https://stripe.com/jobs/search?gh_jid=9001",
        "apply": {"kind": "external", "url": "https://stripe.com/jobs/search?gh_jid=9001"},
        "description": "Build software.",
        "content_hash": "stripe-stale",
        "environment": "live",
    }
    save_job_snapshot(svc.wf, job)
    svc.store.put({
        "pk": f"USER#{UID}", "sk": f"MATCH#{key}", "entity": "match", "job_key": key,
        "score": 76, "auto_eligible": True, "blocked": False,
    })

    app = svc.ensure_application(UID, key)
    assert app["canonical_key"] == "greenhouse:stripe:9001"
    assert store.get(f"USER#{UID}", "APPKEY#greenhouse:stripe:9001")["app_id"] == app["app_id"]
