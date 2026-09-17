import unittest

import helpers  # noqa: F401

from career_agent.scoring import Evidence, hard_filters, heuristic_evidence, score_match, verify_quotes

RESUME = """Asha Rao — B.Tech Computer Science, graduating 2027.
Built a FastAPI service on AWS Lambda with DynamoDB handling 2k requests/day.
Skills: Python, TypeScript, React, SQL, Docker."""

JOB = {"title": "Backend Engineer Intern", "company": "Northwind Labs", "location": "Bengaluru (Hybrid)",
       "requirements": {"required_skills": ["Python", "DynamoDB", "Go"], "preferred_skills": ["React"],
                        "responsibilities": ["Build backend APIs with Python services"], "graduation_years": [2026, 2027]}}


class Scoring(unittest.TestCase):
    def test_heuristic_quotes_only_real_text(self):
        ev = heuristic_evidence(JOB, RESUME)
        by = {s["skill"]: s for s in ev.skills}
        self.assertIsNotNone(by["Python"]["evidence"])
        self.assertIsNone(by["Go"]["evidence"])

    def test_missing_evidence_lowers_score(self):
        prefs = {"roles": ["backend"], "work_modes": ["hybrid", "remote"]}
        facts = {"education": [{"graduation_year": 2027}]}
        full = Evidence(skills=[{"skill": s, "required": True, "evidence": "Python"} for s in ["Python", "DynamoDB", "Go"]],
                        experience=1, experience_evidence=["x"], responsibilities=1, responsibilities_evidence=["x"])
        partial = Evidence(skills=[{"skill": "Python", "required": True, "evidence": "Python"},
                                   {"skill": "Go", "required": True, "evidence": None}], experience=1, responsibilities=1)
        self.assertEqual(score_match(JOB, prefs, facts, full).score, 100)
        self.assertLess(score_match(JOB, prefs, facts, partial).score, 100)

    def test_unknown_graduation_blocks_auto(self):
        m = score_match(JOB, {}, {}, heuristic_evidence(JOB, RESUME))
        self.assertTrue(m.unknowns)
        self.assertFalse(m.auto_eligible)

    def test_excluded_company_blocks(self):
        m = score_match(JOB, {"excluded_companies": ["northwind labs"]}, {"education": [{"graduation_year": 2027}]},
                        heuristic_evidence(JOB, RESUME))
        self.assertTrue(m.blocked)

    def test_verify_quotes_drops_hallucinations(self):
        ev = Evidence(skills=[{"skill": "Kubernetes", "required": True, "evidence": "Managed 40-node Kubernetes clusters"}],
                      experience=0.9, experience_evidence=["Led a team of 12"], responsibilities=0.9)
        ev = verify_quotes(ev, RESUME)
        self.assertIsNone(ev.skills[0]["evidence"])
        self.assertLessEqual(ev.experience, 0.2)

    def test_filters(self):
        f = {x.check: x.status for x in hard_filters(JOB, {"roles": ["frontend"]}, {})}
        self.assertEqual(f["role"], "fail")


if __name__ == "__main__":
    unittest.main()
