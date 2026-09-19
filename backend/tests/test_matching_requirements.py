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
