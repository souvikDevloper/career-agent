import helpers  # noqa: F401

from career_agent import applying, policy
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
