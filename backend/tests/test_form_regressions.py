from test_prepare_flow import UID, make_services, save_job

from career_agent.applying import fit_option, resolve_live_questions
from career_agent.handlers.api import _strip
from career_agent.store import Update


def test_degree_level_alias_does_not_invent_degree_specialization():
    options = [{"label": "Bachelor's Degree", "value": "b"}, {"label": "Master's Degree", "value": "m"}]
    assert fit_option(options, "Bachelor of Technology") == "b"
    assert fit_option(options, "B.Tech") == "b"
    assert fit_option([{"label": "Bachelor of Arts", "value": "ba"}], "Bachelor of Technology") is None


def test_live_education_dates_gpa_and_degree_use_existing_verified_evidence():
    profile = {"facts": {"education": [{"degree": "Bachelor of Technology", "graduation_year": 2027,
                 "evidence": "July 2023 - May 2027 (CGPA: 8.67 / 10)", "verified": True}]}}
    questions = [
        {"id": "degree", "label": "Degree Select One Required", "options": ["Bachelor's Degree", "Master's Degree"], "context": {"section": "education", "index": 0}},
        {"id": "start", "label": "Year", "context": {"section": "education", "index": 0, "date_field": "start", "date_part": "year"}},
        {"id": "end", "label": "Year", "context": {"section": "education", "index": 0, "date_field": "end", "date_part": "year"}},
        {"id": "gpa", "label": "Overall Result (GPA)", "context": {"section": "education", "index": 0}},
    ]
    assert {a["id"]: a["value"] for a in resolve_live_questions(profile, questions)} == {
        "degree": "Bachelor's Degree", "start": "2023", "end": "2027", "gpa": "8.67"}


def test_match_list_and_existing_application_use_current_eligibility_without_model(monkeypatch):
    svc, store = make_services()
    job = save_job(svc)
    job["requirements"] = {"min_years": 1}
    store.update(Update(f"USER#{UID}", f"MATCH#{job['job_key']}", set={"job": job, "blocked": True, "auto_eligible": False}))
    old = svc.ensure_application(UID, job["job_key"])
    svc.profiles.correct(UID, {"years_experience": 2})
    monkeypatch.setattr(svc.matcher, "evidence_for", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No new model call needed")))
    match = svc.matcher.list(UID)[0]
    assert not match["blocked"] and match["auto_eligible"]
    app = svc.ensure_application(UID, job["job_key"])
    assert app["app_id"] == old["app_id"]
    assert not app["blocked"] and app["auto_eligible"]


def test_legacy_watch_can_be_listed_and_queued_alongside_current_watch(monkeypatch):
    from career_agent import discovery
    svc, store = make_services()
    store.put({"pk": f"USER#{UID}", "sk": "WATCH#w_legacy", "enabled": True, "keywords": "intern",
               "gsi1pk": "WATCH#enabled", "gsi1sk": f"USER#{UID}"})
    svc.create_watch(UID, "software", 30)
    monkeypatch.setattr(discovery, "all_sources", lambda: [])
    summary = svc.run_monitor(force=True)
    assert summary["fanout"] == 2
    legacy = store.get(f"USER#{UID}", "WATCH#w_legacy")
    assert legacy["watch_id"] == "w_legacy" and legacy["user_id"] == UID
    assert _strip({"sk": "WATCH#w_old"})["watch_id"] == "w_old"
