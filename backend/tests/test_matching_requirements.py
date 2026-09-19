import helpers  # noqa: F401

from career_agent.matching import _complete_skill_evidence


def test_missing_required_skill_cannot_disappear_from_scoring_denominator():
    requirements = {"required_skills": ["Python", "Go", "SQL"], "preferred_skills": ["Docker"]}
    model_skills = [
        {"skill": "Python", "required": True, "evidence": "Built Python services"},
        {"skill": "SQL", "required": True, "evidence": "SQL"},
    ]
    got = _complete_skill_evidence(model_skills, requirements)
    by = {row["skill"].lower(): row for row in got}
    assert set(by) == {"python", "go", "sql", "docker"}
    assert by["go"]["required"] is True
    assert by["go"]["evidence"] is None
    assert by["docker"]["required"] is False


def test_requirements_override_model_required_flag():
    got = _complete_skill_evidence(
        [{"skill": "Docker", "required": True, "evidence": "Docker"}],
        {"required_skills": [], "preferred_skills": ["Docker"]},
    )
    assert got[0]["required"] is False


def test_unavailable_model_uses_one_bounded_call_then_provisional_evidence(monkeypatch):
    from career_agent import llm
    from career_agent.matching import Matcher
    wf, _store, _clock = helpers.make()
    matcher = Matcher(wf, None)
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(kwargs)
        raise llm.ModelUnavailable("timed out")
    monkeypatch.setattr(llm, "json_call", unavailable)
    evidence, _, explanation = matcher.evidence_for("u1", {"title": "Software Engineer"},
        {"resume_text": "Python"}, is_judge=False, correlation_id=None, timeout_seconds=12)
    assert len(calls) == 1
    assert calls[0]["timeout_seconds"] == 12
    assert calls[0]["repair"] is False
    assert evidence.extractor.startswith("heuristic")
    assert "keyword" in explanation


def test_evidence_reports_the_provider_that_actually_answered(monkeypatch):
    from career_agent import llm
    from career_agent.matching import Matcher
    wf, _store, _clock = helpers.make()
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("FALLBACK_MODEL_ID", "actual-model")
    monkeypatch.setattr(llm, "json_call", lambda *a, **k: {"requirements": {}, "skills": []})
    evidence, _, _ = Matcher(wf, None).evidence_for("u1", {"title": "Engineer"},
        {"resume_text": "Python"}, is_judge=False, correlation_id=None)
    assert evidence.extractor == "anthropic:actual-model"
