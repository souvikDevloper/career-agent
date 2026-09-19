"""Normalization for the public job boards.

Network-free: each board's payload shape is pinned here, so a field the matcher
depends on cannot quietly stop being populated.
"""

import unittest

from career_agent.scoring import work_mode_of
from career_agent.sources import adzuna, amazon, ashby, greenhouse, lever, oraclehcm, workday


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


class GreenhouseCanonicalKey(unittest.TestCase):
    """The board supplies requisition_id and boards abuse the field.

    Stripe returns the literal sentence "See Opening ID" for every one of its
    665 postings. Trusting it gave the whole board one canonical key, and the
    deduplicator then collapsed 665 openings into 2 - so a search for Stripe
    backend roles returned nothing.
    """

    def raw(self, job_id, requisition):
        return {"id": job_id, "title": "Backend Engineer", "location": {"name": "Bengaluru"},
                "content": "<p>Build APIs.</p>", "absolute_url": f"https://boards.greenhouse.io/x/{job_id}",
                "requisition_id": requisition, "updated_at": "2026-09-01T00:00:00Z", "departments": []}

    def test_a_placeholder_requisition_falls_back_to_the_posting_id(self):
        for junk in ("See Opening ID", "see opening id", "", "N/A - see posting", "  "):
            a = greenhouse.normalize("stripe", self.raw(1, junk))
            b = greenhouse.normalize("stripe", self.raw(2, junk))
            self.assertNotEqual(a["canonical_key"], b["canonical_key"], f"{junk!r} collapsed two postings")

    def test_a_real_requisition_is_used(self):
        job = greenhouse.normalize("stripe", self.raw(1, "REQ-4821"))
        self.assertTrue(job["canonical_key"].endswith("REQ-4821"))

    def test_the_same_posting_keeps_a_stable_key(self):
        self.assertEqual(greenhouse.normalize("stripe", self.raw(7, "REQ-1"))["canonical_key"],
                         greenhouse.normalize("stripe", self.raw(7, "REQ-1"))["canonical_key"])


class WorkdayNormalize(unittest.TestCase):
    """Most large employers run their careers site on Workday, and every one of
    them answers the same public JSON its own pages call."""

    def raw(self, **over):
        base = {"title": "Staff Software Engineer",
                "externalPath": "/job/Chennai-Tamil-Nadu-India/Staff-Software-Engineer_R0138155",
                "locationsText": "Chennai, Tamil Nadu, India",
                "postedOn": "Posted Today", "bulletFields": ["R0138155"]}
        base.update(over)
        return base

    def test_the_requisition_becomes_the_identity(self):
        job = workday.normalize("paypal", "wd1", "jobs", self.raw())
        self.assertEqual(job["external_id"], "R0138155")
        self.assertEqual(job["canonical_key"], "workday:paypal:R0138155")

    def test_a_missing_requisition_falls_back_to_the_path(self):
        a = workday.normalize("paypal", "wd1", "jobs", self.raw(bulletFields=[]))
        b = workday.normalize("paypal", "wd1", "jobs",
                              self.raw(bulletFields=[], externalPath="/job/Pune/Other-Role_R999"))
        self.assertNotEqual(a["canonical_key"], b["canonical_key"])

    def test_the_url_is_the_page_a_person_can_open(self):
        job = workday.normalize("paypal", "wd1", "jobs", self.raw())
        self.assertEqual(job["url"],
                         "https://paypal.wd1.myworkdayjobs.com/en-US/jobs"
                         "/job/Chennai-Tamil-Nadu-India/Staff-Software-Engineer_R0138155")
        self.assertEqual(job["apply"]["kind"], "external")

    def test_remote_is_read_from_the_location_text(self):
        self.assertEqual(workday.normalize("x", "wd1", "s", self.raw(locationsText="Remote, India"))["work_mode"], "remote")
        self.assertIsNone(workday.normalize("x", "wd1", "s", self.raw())["work_mode"])

    def test_the_description_is_left_for_later(self):
        """The listing does not carry it; fetching it for every posting on every
        poll would be hundreds of requests for text nobody reads."""
        self.assertEqual(workday.normalize("paypal", "wd1", "jobs", self.raw())["description"], "")

    def test_a_malformed_board_is_refused_before_it_reaches_a_url(self):
        for bad in ("paypal", "paypal:jobs", "paypal:x1:jobs", "../etc:wd1:jobs", ""):
            with self.assertRaises(ValueError, msg=bad):
                workday.parse_spec(bad)

    def test_a_valid_board_parses(self):
        self.assertEqual(workday.parse_spec("paypal:wd1:jobs"), ("paypal", "wd1", "jobs"))
        self.assertEqual(workday.parse_spec("nvidia:wd5:NVIDIAExternalCareerSite"),
                         ("nvidia", "wd5", "NVIDIAExternalCareerSite"))


class OracleHcmNormalize(unittest.TestCase):
    """The other half of the large-employer world runs on Oracle rather than
    Workday; JPMorgan Chase alone publishes over seven thousand openings."""

    def raw(self, **over):
        base = {"Id": "210577366", "Title": "Lead Software Engineer",
                "PrimaryLocation": "Bengaluru, Karnataka, India", "PrimaryLocationCountry": "IN",
                "PostedDate": "2026-09-16", "ShortDescriptionStr": "Build payment systems.",
                "ExternalQualificationsStr": "Java, Python.", "WorkplaceType": "Hybrid",
                "JobFamily": "Software Engineering", "JobFunction": "Technology"}
        base.update(over)
        return base

    def test_required_fields(self):
        job = oraclehcm.normalize("jpmc", "CX_1001", self.raw())
        for key in ("job_key", "canonical_key", "company", "title", "url", "content_hash", "connector"):
            self.assertTrue(job[key], f"{key} is empty")
        self.assertEqual(job["environment"], "live")

    def test_the_employer_work_mode_is_kept(self):
        for given, expected in (("Hybrid", "hybrid"), ("Remote", "remote"), ("Onsite", "onsite")):
            self.assertEqual(oraclehcm.normalize("jpmc", "CX_1001", self.raw(WorkplaceType=given))["work_mode"], expected)

    def test_description_joins_the_parts_the_employer_published(self):
        got = oraclehcm.normalize("jpmc", "CX_1001", self.raw())["description"]
        self.assertIn("Build payment systems", got)
        self.assertIn("Java, Python", got)

    def test_country_is_carried_for_filtering(self):
        self.assertEqual(oraclehcm.normalize("jpmc", "CX_1001", self.raw())["country"], "IN")

    def test_a_country_may_be_pinned_in_the_spec(self):
        self.assertEqual(oraclehcm.parse_spec("jpmc:CX_1001:IN"), ("jpmc", "CX_1001", "IN"))
        self.assertEqual(oraclehcm.parse_spec("jpmc:CX_1001"), ("jpmc", "CX_1001", None))
        self.assertEqual(oraclehcm.parse_spec("jpmc:CX_1001:in"), ("jpmc", "CX_1001", "IN"))

    def test_a_malformed_spec_is_refused_before_it_reaches_a_url(self):
        for bad in ("jpmc", "", "../x:CX_1001", "jpmc:CX_1001:INDIA", "jpmc:CX 1001"):
            with self.assertRaises(ValueError, msg=bad):
                oraclehcm.parse_spec(bad)


class AmazonNormalize(unittest.TestCase):
    def raw(self, **over):
        base = {"id_icims": "10552765", "title": "Software Dev Engineer Intern",
                "job_path": "/en/jobs/10552765/software-dev-engineer-intern",
                "normalized_location": "Bengaluru, Karnataka, IND", "country_code": "IND",
                "posted_date": "September 18, 2026", "description_short": "Build services.",
                "basic_qualifications": "Python, data structures.",
                "preferred_qualifications": "AWS experience.", "job_category": "Software Development"}
        base.update(over)
        return base

    def test_qualifications_are_kept_as_written(self):
        """This board publishes requirements as requirements rather than prose."""
        got = amazon.normalize(self.raw())["description"]
        self.assertIn("Basic qualifications", got)
        self.assertIn("Python, data structures", got)
        self.assertIn("Preferred qualifications", got)

    def test_an_internship_is_recognised_from_the_title(self):
        """is_intern is documented but absent from the search response."""
        self.assertEqual(amazon.normalize(self.raw())["employment_type"], "internship")
        self.assertEqual(amazon.normalize(self.raw(title="Internship - Cloud"))["employment_type"], "internship")

    def test_a_word_merely_starting_with_intern_is_not_one(self):
        for title in ("International Trade Manager", "Internal Audit Lead"):
            self.assertIsNone(amazon.normalize(self.raw(title=title))["employment_type"], title)

    def test_the_url_is_the_posting_a_person_can_open(self):
        job = amazon.normalize(self.raw())
        self.assertEqual(job["url"], "https://www.amazon.jobs/en/jobs/10552765/software-dev-engineer-intern")
        self.assertEqual(job["apply"]["kind"], "external")

    def test_country_is_carried_for_filtering(self):
        self.assertEqual(amazon.normalize(self.raw())["country"], "IND")

    def test_spec_parsing(self):
        self.assertEqual(amazon.parse_spec("IND"), ("IND", ""))
        self.assertEqual(amazon.parse_spec("IND:intern"), ("IND", "intern"))
        for bad in ("", "INDIA_LONG_NAME", "IND:" + "x" * 80):
            with self.assertRaises(ValueError, msg=bad):
                amazon.parse_spec(bad)

    def test_the_hiring_entity_does_not_replace_the_company(self):
        """company_name is the legal entity - "ASSPL - Karnataka". Nobody searches
        for that, and it makes an Amazon role look like an unknown company."""
        job = amazon.normalize(self.raw(company_name="ASSPL - Karnataka"))
        self.assertEqual(job["company"], "Amazon")
        self.assertEqual(job["legal_entity"], "ASSPL - Karnataka")


class TestGreenhousePublishesTheRealApplicationForm:
    """The same unauthenticated endpoint that serves a posting also serves its
    application form. That is what makes a packet checkable before a browser is
    opened: we know every field the employer will receive, its type, and whether
    it is required, instead of guessing and discovering the gap at submit time.
    """

    QUESTIONS = [
        {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text", "values": []}]},
        {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file", "values": []}]},
        {"label": "Why this role?", "required": False, "fields": [{"name": "cover_letter_text", "type": "textarea", "values": []}]},
        {"label": "Are you based in India?", "required": True,
         "fields": [{"name": "question_1", "type": "multi_value_single_select",
                     "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
    ]

    def form(self):
        return greenhouse.parse_questions(self.QUESTIONS)

    def test_every_greenhouse_type_maps_to_one_the_packet_builder_understands(self):
        kinds = {f["name"]: f["type"] for f in self.form()["fields"]}
        assert kinds == {"first_name": "text", "resume": "file",
                         "cover_letter_text": "textarea", "question_1": "select"}

    def test_required_travels_from_the_question_to_each_of_its_fields(self):
        required = {f["name"]: f["required"] for f in self.form()["fields"]}
        assert required["first_name"] is True and required["cover_letter_text"] is False

    def test_choices_keep_their_labels_and_values_as_strings(self):
        choice = next(f for f in self.form()["fields"] if f["name"] == "question_1")
        assert choice["options"] == [{"label": "Yes", "value": "1"}, {"label": "No", "value": "0"}]

    def test_the_signature_changes_when_the_employer_changes_the_form(self):
        """Approval is bound to the form we read; a changed form must not reuse it."""
        altered = [*self.QUESTIONS[:3],
                   {"label": "Are you based in India?", "required": True,
                    "fields": [{"name": "question_1", "type": "multi_value_single_select",
                                "values": [{"label": "Yes", "value": 1}]}]}]
        assert greenhouse.parse_questions(altered)["signature"] != self.form()["signature"]

    def test_a_question_with_no_field_name_is_skipped_rather_than_crashing(self):
        assert greenhouse.parse_questions([{"label": "Broken", "required": True, "fields": [{"type": "input_text"}]}])["fields"] == []


class TestGreenhouseSaysWhoHostsTheForm:
    """Connector capability is not posting capability.

    Twilio, Reddit and GitLab serve their application on job-boards.greenhouse.io.
    Stripe, Databricks and Rubrik embed the same Greenhouse form in their own
    careers site, behind their own bot protection. Reading which from the posting
    keeps this out of a hand-curated list that would silently go stale.
    """

    def job(self, absolute_url):
        return greenhouse.normalize("twilio", {
            "id": 8177722, "title": "Software Engineer", "content": "", "absolute_url": absolute_url,
            "location": {"name": "Remote - India"}, "updated_at": "2026-09-01T00:00:00Z",
        })

    def test_a_greenhouse_hosted_posting_is_marked_submittable(self):
        apply = self.job("https://job-boards.greenhouse.io/twilio/jobs/8177722")["apply"]
        assert apply["kind"] == "hosted_form"
        assert apply["url"] == "https://job-boards.greenhouse.io/twilio/jobs/8177722"

    def test_a_posting_embedded_on_the_employers_site_is_not(self):
        apply = self.job("https://stripe.com/jobs/search?gh_jid=8172487")["apply"]
        assert apply["kind"] == "external"
        assert apply["url"] == "https://stripe.com/jobs/search?gh_jid=8172487"

    def test_the_canonical_url_is_rebuilt_rather_than_trusted(self):
        """The board's own link may carry tracking; the form is addressed directly."""
        apply = self.job("https://job-boards.greenhouse.io/twilio/jobs/8177722?utm_source=x")["apply"]
        assert apply["url"] == "https://job-boards.greenhouse.io/twilio/jobs/8177722"

    def test_a_posting_with_no_url_does_not_claim_to_be_submittable(self):
        assert self.job(None)["apply"] == {"kind": "external", "url": None}


class TestAmazonIsSearchedNotMirrored:
    """Amazon India publishes 2,322 openings; paging all of them takes 98 seconds.

    The poller therefore kept the 400 most recent, and a person searching for an
    SDE 1 in Bengaluru was told none existed while five were live - they simply
    were not among the newest 400. Asking amazon.jobs to run the search answers
    the same question completely, in about a second.
    """

    def captured(self, monkeypatch):
        seen = {}

        def fake(url, hosts, **kw):
            seen["url"] = url
            return {"hits": 8, "jobs": [{"id_icims": "10525636", "title": "SDE-1 (FTC)",
                                         "normalized_location": "Bengaluru, Karnataka, IND",
                                         "job_path": "/en/jobs/10525636/sde-1-ftc"}]}

        monkeypatch.setattr(amazon, "fetch_json", fake)
        return seen

    def test_the_query_is_handed_to_amazon_rather_than_filtered_here(self, monkeypatch):
        seen = self.captured(monkeypatch)
        jobs = amazon.search("IND", "SDE 1")
        assert "base_query=SDE+1" in seen["url"]
        assert "country=IND" in seen["url"]
        assert len(jobs) == 1 and jobs[0]["external_id"] == "10525636"

    def test_an_empty_query_still_asks_for_the_country(self, monkeypatch):
        seen = self.captured(monkeypatch)
        amazon.search("IND", "")
        assert "base_query" not in seen["url"]
        assert "country=IND" in seen["url"]

    def test_the_page_size_is_bounded(self, monkeypatch):
        """One request, never an unbounded page that times out the caller."""
        seen = self.captured(monkeypatch)
        amazon.search("IND", "x", limit=10_000)
        assert "result_limit=100" in seen["url"]

    def test_results_are_ranked_by_relevance_not_recency(self, monkeypatch):
        """Recency is what hid the SDE 1 roles behind 400 newer postings."""
        seen = self.captured(monkeypatch)
        amazon.search("IND", "SDE 1")
        assert "sort=relevant" in seen["url"]


class TestAdzunaIsSecondClassOnPurpose:
    """An aggregator holds a copy of someone else's posting.

    It buys breadth - Indian employers with no public ATS feed at all - and pays
    for it in fidelity: truncated descriptions, and an apply link that redirects
    to whoever actually owns the posting. So it discovers and scores, and is never
    something we could fill a form on.
    """

    RAW = {
        "id": "4839201",
        "title": "Software Engineer",
        "company": {"display_name": "Zeta Suite"},
        "location": {"display_name": "Bengaluru, Karnataka", "area": ["India", "Karnataka", "Bengaluru"]},
        "description": "Build payment systems. Remote friendly.",
        "redirect_url": "https://www.adzuna.in/land/ad/4839201",
        "created": "2026-09-14T00:00:00Z",
        "contract_time": "full_time",
        "category": {"label": "IT Jobs"},
    }

    def job(self):
        return adzuna.normalize("in", self.RAW)

    def test_it_normalises_into_the_same_shape_as_every_other_board(self):
        job = self.job()
        assert job["company"] == "Zeta Suite"
        assert job["location"] == "Bengaluru, Karnataka"
        assert job["published_at"] == "2026-09-14T00:00:00Z"
        assert job["connector"] == adzuna.SOURCE

    def test_applying_is_always_a_handoff(self):
        """A redirect is not a form, so it can never be marked submittable."""
        assert self.job()["apply"]["kind"] == "external"

    def test_the_spec_accepts_a_country_and_an_optional_query(self):
        assert adzuna.parse_spec("in") == ("in", "")
        assert adzuna.parse_spec("in:python") == ("in", "python")

    def test_a_malformed_spec_is_rejected_rather_than_guessed(self):
        """A country code, not a country name - guessing which was meant is how a
        board silently polls the wrong index."""
        for bad in ("india", "IN", "in:", "x"):
            try:
                adzuna.parse_spec(bad)
            except ValueError:
                continue
            raise AssertionError(f"{bad!r} should not parse")

    def test_without_a_key_it_says_so_instead_of_calling(self, monkeypatch):
        """Registered but unconfigured is a state the UI can explain; a silent
        failed call is not."""
        monkeypatch.setenv("ADZUNA_KEY_PARAM", "")
        monkeypatch.setenv("ADZUNA_KEY", "")
        monkeypatch.setattr(adzuna, "_creds", None)
        try:
            adzuna.fetch_board("in")
        except ValueError as exc:
            assert "not configured" in str(exc)
        else:
            raise AssertionError("a missing key should be reported, not called with")
