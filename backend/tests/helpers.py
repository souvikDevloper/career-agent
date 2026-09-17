import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from career_agent import policy  # noqa: E402
from career_agent.store import MemoryStore  # noqa: E402
from career_agent.util import FixedClock  # noqa: E402
from career_agent.workflow import Principal, Workflow  # noqa: E402

T0 = 1_789_000_000.0  # 2026-09-10 (UTC)

JOB = {
    "job_key": "northwind-test-portal:nw-101", "source": "northwind-test-portal", "company": "Northwind Labs",
    "title": "Backend Engineer Intern", "location": "Bengaluru (Hybrid)", "url": "https://example.test/jobs/nw-101",
}


def make(engine=None):
    policy.set_engine(engine or policy.ReferenceEngine())
    store = MemoryStore()
    clock = FixedClock(T0)
    wf = Workflow(store, clock)
    return wf, store, clock


def packet(**over):
    base = {
        "target": {"url": "https://example.test/apply/nw-101", "connector": "northwind-test-portal"},
        "job_snapshot_hash": "jobhash", "profile_version": 1, "resume_key": "resumes/u1/r1.pdf",
        "answers": {"full_name": "Asha Rao", "email": "asha@example.test"}, "attachments": ["resume"],
        "consents": {"privacy": True}, "form_signature": "sig-1", "cover_note": "I built ...", "unknown_required": [],
    }
    base.update(over)
    return base


def new_app(wf, uid="u1", score=85, eligible=True, connector="northwind-test-portal"):
    return wf.create_application(uid, JOB, {"score": score, "auto_eligible": eligible, "blocked": False}, connector)


P = Principal
