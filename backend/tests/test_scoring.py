import unittest

import helpers  # noqa: F401

from career_agent.scoring import (FAIL, PASS, UNKNOWN, Evidence, derived_years, hard_filters,
                                  heuristic_evidence, score_match, verify_quotes)

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
                        experience=1, experience_evidence=["a", "b", "c"],
                        responsibilities=1, responsibilities_evidence=["d", "e", "f"])
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


class TestExperienceIsWorkedOutFromTheResume:
    """"It does not know my experience" was a real complaint about real data.

    A profile with no stated total is not a person with no experience. The dates
    are already on the roles the extractor pulled out, so every posting with a
    minimum-years requirement was reporting "no verified total" while the answer
    sat one subtraction away.
    """

    def test_an_ongoing_role_counts_up_to_today(self):
        years = derived_years({"experience": [{"start": "Jan 2024", "end": "Present"}]})
        assert years is not None and years > 2

    def test_overlapping_roles_are_counted_once(self):
        """Two jobs held in the same year is one year of experience."""
        overlapping = derived_years({"experience": [
            {"start": "Jan 2023", "end": "Dec 2024"},
            {"start": "Jun 2023", "end": "Jun 2024"}]})
        assert overlapping == 1.9

    def test_separate_roles_are_added(self):
        assert derived_years({"experience": [
            {"start": "2021", "end": "2022"}, {"start": "2024", "end": "2025"}]}) == 2.0

    def test_a_bare_year_range_is_not_stretched_to_its_maximum(self):
        """"2021 - 2022" is one year, not two. Overstating is the one direction
        this must not be wrong in - it goes onto an application."""
        assert derived_years({"experience": [{"start": "2021", "end": "2022"}]}) == 1.0

    def test_a_short_internship_is_a_fraction_of_a_year(self):
        assert derived_years({"experience": [{"start": "May 2025", "end": "Aug 2025"}]}) == 0.2

    def test_iso_and_slashed_dates_both_parse(self):
        assert derived_years({"experience": [{"start": "2023-06", "end": "2025-06"}]}) == 2.0
        assert derived_years({"experience": [{"start": "06/2023", "end": "06/2025"}]}) == 2.0

    def test_an_undated_role_is_still_unknown_rather_than_invented(self):
        assert derived_years({"experience": [{"title": "Intern"}]}) is None
        assert derived_years({"experience": []}) is None


class TestTheExperienceFilterUsesIt:
    JOB = {"title": "Backend Engineer", "requirements": {"min_years": 2}}

    def result(self, facts):
        return next(f for f in hard_filters(self.JOB, {}, facts) if f.check == "experience_years")

    def test_dated_roles_answer_the_requirement_instead_of_shrugging(self):
        got = self.result({"experience": [{"start": "Jan 2023", "end": "Present"}]})
        assert got.status == PASS
        assert "from the dates on your roles" in got.detail

    def test_a_stated_total_is_preferred_over_the_derived_one(self):
        got = self.result({"years_experience": 5, "experience": [{"start": "2025", "end": "Present"}]})
        assert got.status == PASS and "stated on your profile" in got.detail

    def test_too_little_experience_is_a_fail_not_an_unknown(self):
        got = self.result({"experience": [{"start": "May 2026", "end": "Present"}]})
        assert got.status == FAIL

    def test_only_a_resume_with_no_dates_at_all_is_unknown(self):
        got = self.result({"experience": [{"title": "Intern"}]})
        assert got.status == UNKNOWN
        assert "no dated roles" in got.detail


class TestAProvisionalScoreIsNotCached:
    """A keyword score is a stand-in, and must not settle in as the answer.

    Two copies of the same Amazon SDE-1 posting sat at 81 and 39 with identical
    descriptions. The difference was which one the model answered for: the other
    timed out, fell back to the keyword extractor, and the cache then returned
    that number for good. The extractor cannot even reach the same range - with
    no extracted requirements it takes the neutral half-credit on skills - so the
    two numbers were never comparable, and they were being compared.
    """

    class Store:
        def __init__(self, existing):
            self.existing = existing
            self.written = []

        def get(self, pk, sk, consistent=True):
            return self.existing

        def put(self, item, condition=None):
            self.written.append(item)

    def matcher(self, monkeypatch, existing, extractor):
        from career_agent.matching import Matcher

        wf = type("WF", (), {})()
        wf.store = self.Store(existing)
        wf.settings = lambda uid: {"preferences": {}}
        wf.clock = type("C", (), {"iso": staticmethod(lambda: "2026-09-19T00:00:00Z")})()
        wf.reserve_usage = lambda *a, **k: True
        profiles = type("P", (), {})()
        profiles.current = lambda uid: {"version": 1, "facts": {}, "resume_text": "python go"}
        m = Matcher(wf, profiles)
        monkeypatch.setattr(m, "evidence_for",
                            lambda *a, **k: (Evidence(skills=[], extractor=extractor), {}, "why"))
        return m

    def job(self):
        return {"job_key": "amazon:1", "title": "SDE-1 (FTC)", "company": "Amazon", "content_hash": "h1"}

    def cached(self, extractor, fingerprint):
        return {"fingerprint": fingerprint, "score": 39, "extractor": extractor}

    def fingerprint_of(self, m, job):
        from career_agent.scoring import RUBRIC_VERSION
        from career_agent.util import sha256
        return sha256([job.get("content_hash"), 1, {}, RUBRIC_VERSION])

    def test_a_model_score_is_reused(self, monkeypatch):
        job = self.job()
        m = self.matcher(monkeypatch, None, "bedrock:x")
        fp = self.fingerprint_of(m, job)
        m.store.existing = self.cached("bedrock:us.amazon.nova", fp)
        assert m.match("u1", job)["score"] == 39, "a real score should come straight from the cache"
        assert m.store.written == []

    def test_a_keyword_score_is_scored_again(self, monkeypatch):
        job = self.job()
        m = self.matcher(monkeypatch, None, "bedrock:x")
        fp = self.fingerprint_of(m, job)
        m.store.existing = self.cached("heuristic", fp)
        m.match("u1", job)
        assert len(m.store.written) == 1, "a provisional score must be re-scored, not returned"
        assert m.store.written[0]["extractor"] == "bedrock:x"


class TestRubricV2Semantics:
    def test_no_saved_preferences_are_neutral_not_free_ten_points(self):
        ev = Evidence(skills=[], experience=0, responsibilities=0)
        got = score_match({"title": "Engineer", "company": "Acme", "requirements": {}}, {}, {}, ev)
        assert got.components["preferences"] == 5.0

    def test_saved_role_mismatch_is_a_preference_not_an_eligibility_block(self):
        ev = Evidence(skills=[], experience=0, responsibilities=0)
        got = score_match({"title": "Data Engineer", "company": "Acme", "requirements": {}},
                          {"roles": ["frontend"]}, {}, ev)
        role = next(f for f in got.filters if f.check == "role")
        assert role.status == FAIL and role.mandatory is False
        assert got.blocked is False

    def test_saved_location_mismatch_is_not_a_hard_block(self):
        ev = Evidence(skills=[], experience=0, responsibilities=0)
        got = score_match({"title": "Engineer", "company": "Acme", "location": "Pune", "requirements": {}},
                          {"locations": ["Bengaluru"]}, {}, ev)
        loc = next(f for f in got.filters if f.check == "location")
        assert loc.status == FAIL and loc.mandatory is False
        assert got.blocked is False

    def test_confirmed_no_work_authorization_is_a_real_block(self):
        job = {"title": "Engineer", "company": "Acme",
               "requirements": {"work_authorization_required": True}}
        facts = {"work_authorization": {"verified": True, "value": "No"}}
        got = score_match(job, {}, facts, Evidence())
        auth = next(f for f in got.filters if f.check == "work_authorization")
        assert auth.status == FAIL
        assert got.blocked is True

    def test_subjective_components_need_resume_evidence(self):
        job = {"title": "Engineer", "company": "Acme", "requirements": {}}
        no_quotes = score_match(job, {}, {}, Evidence(experience=1, responsibilities=1))
        one_quote = score_match(job, {}, {}, Evidence(
            experience=1, experience_evidence=["one"],
            responsibilities=1, responsibilities_evidence=["one"]))
        assert no_quotes.components["experience"] == 6.0
        assert no_quotes.components["responsibilities"] == 4.0
        assert one_quote.components["experience"] == 22.5
        assert one_quote.components["responsibilities"] == 15.0
        assert one_quote.score > no_quotes.score
