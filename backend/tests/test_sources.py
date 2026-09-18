"""Normalization for the public job boards.

Network-free: each board's payload shape is pinned here, so a field the matcher
depends on cannot quietly stop being populated.
"""

import unittest

from career_agent.scoring import work_mode_of
from career_agent.sources import ashby, lever


class LeverNormalize(unittest.TestCase):
    def raw(self, **over):
        base = {
            "id": "abc-123",
            "text": "Backend Engineer Intern",
            "categories": {"location": "Baltimore, MD", "team": "Engineering", "commitment": "Intern"},
            "descriptionPlain": "Build Python services on AWS.",
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
            "applyUrl": "https://jobs.lever.co/acme/abc-123/apply",
            "workplaceType": "remote",
            "createdAt": 1750000000000,
        }
        base.update(over)
        return base

    def test_employer_work_mode_is_preserved(self):
        """All three modes come through; guessing from the location loses two of them."""
        for mode in ("remote", "hybrid", "onsite"):
            job = lever.normalize("acme", self.raw(workplaceType=mode))
            self.assertEqual(job["work_mode"], mode)
            self.assertEqual(work_mode_of(job), mode)

    def test_unknown_work_mode_defers_to_scoring(self):
        job = lever.normalize("acme", self.raw(workplaceType=""))
        self.assertIsNone(job["work_mode"])

    def test_required_fields_are_populated(self):
        job = lever.normalize("acme", self.raw())
        for key in ("job_key", "canonical_key", "source", "company", "title", "url", "content_hash", "connector"):
            self.assertTrue(job[key], f"{key} is empty")
        self.assertEqual(job["environment"], "live")

    def test_apply_is_a_handoff_not_an_automated_submission(self):
        job = lever.normalize("acme", self.raw())
        self.assertEqual(job["apply"]["kind"], "external")

    def test_content_hash_tracks_the_fields_that_matter(self):
        a = lever.normalize("acme", self.raw())
        self.assertEqual(a["content_hash"], lever.normalize("acme", self.raw())["content_hash"])
        self.assertNotEqual(a["content_hash"], lever.normalize("acme", self.raw(text="Other role"))["content_hash"])

    def test_board_token_is_validated_before_it_reaches_a_url(self):
        with self.assertRaises(ValueError):
            lever.fetch_board("../../etc/passwd")


class AshbyNormalize(unittest.TestCase):
    def raw(self, **over):
        base = {
            "id": "xyz-9",
            "title": "Cloud Engineer Intern",
            "location": "Pune",
            "secondaryLocations": [{"location": "Bengaluru"}],
            "isRemote": False,
            "descriptionPlain": "AWS, Lambda, DynamoDB.",
            "jobUrl": "https://jobs.ashbyhq.com/acme/xyz-9",
            "publishedAt": "2026-09-01T00:00:00Z",
        }
        base.update(over)
        return base

    def test_secondary_locations_are_kept(self):
        job = ashby.normalize("acme", self.raw())
        self.assertIn("Pune", job["location"])
        self.assertIn("Bengaluru", job["location"])

    def test_remote_flag_is_honoured(self):
        self.assertEqual(ashby.normalize("acme", self.raw(isRemote=True))["work_mode"], "remote")
        self.assertIsNone(ashby.normalize("acme", self.raw())["work_mode"])

    def test_required_fields_are_populated(self):
        job = ashby.normalize("acme", self.raw())
        for key in ("job_key", "source", "company", "title", "url", "content_hash", "connector"):
            self.assertTrue(job[key], f"{key} is empty")

    def test_board_token_is_validated_before_it_reaches_a_url(self):
        with self.assertRaises(ValueError):
            ashby.fetch_board("bad token/../x")


if __name__ == "__main__":
    unittest.main()
