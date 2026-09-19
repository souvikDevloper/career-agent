"""Which openings a search is allowed to return.

The filter used to be an OR: one matching word qualified a job. So "microsoft
internship" matched every posting containing the word "internship", and a search
for a company this product does not cover came back full of confident results
from a company the person never asked about. That is worse than an empty
result - it reads as a product that makes things up.
"""

from __future__ import annotations

from helpers import T0  # noqa: F401  (adds src/ to sys.path)

from career_agent.discovery import keyword_filter

PREFS: dict = {"roles": [], "excluded_companies": []}


def job(company, title, location="Bengaluru", description="", source="greenhouse-public", key=None):
    return {"company": company, "title": title, "location": location, "description": description,
            "source": source, "canonical_key": key or f"{company}:{title}:{location}".lower(),
            "first_seen_at": "2026-09-18T00:00:00Z"}


CORPUS = [
    job("Northwind Labs", "Backend Engineer Intern", description="Python internship building services.",
        source="northwind-test-portal"),
    job("Northwind Labs", "Cloud Engineer Intern (AWS)", description="AWS internship.", source="northwind-test-portal"),
    job("Gitlab", "Backend Engineer, Ruby", description="Remote backend engineering."),
    job("Databricks", "Software Engineer Intern", description="Distributed systems internship."),
    job("Linear", "Product Engineer", description="TypeScript product work."),
]


class TestTheBugThatWasReported:
    def test_a_company_we_do_not_cover_returns_nothing(self):
        """The reported failure: this returned six test-employer jobs."""
        assert keyword_filter(CORPUS, "microsoft internship", PREFS) == []

    def test_it_does_not_fall_back_to_unrelated_results(self):
        for query in ("google sde", "amazon internship", "netflix backend", "tesla engineer"):
            assert keyword_filter(CORPUS, query, PREFS) == [], f"{query!r} invented results"

    def test_a_company_we_do_cover_is_found(self):
        got = keyword_filter(CORPUS, "gitlab backend", PREFS)
        assert [j["company"] for j in got] == ["Gitlab"]


class TestEveryWordMustMatch:
    def test_all_terms_required(self):
        got = keyword_filter(CORPUS, "backend internship", PREFS)
        # Gitlab's backend role is not an internship; Databricks' internship is not backend.
        assert [j["company"] for j in got] == ["Northwind Labs"]

    def test_one_missing_term_disqualifies(self):
        assert keyword_filter(CORPUS, "backend kubernetes", PREFS) == []

    def test_a_single_term_still_works(self):
        assert {j["company"] for j in keyword_filter(CORPUS, "internship", PREFS)} == {"Northwind Labs", "Databricks"}

    def test_filler_words_are_ignored(self):
        """'find me relevant backend jobs' must behave like 'backend'."""
        plain = keyword_filter(CORPUS, "backend", PREFS)
        wordy = keyword_filter(CORPUS, "please find me some relevant backend jobs", PREFS)
        assert [j["canonical_key"] for j in plain] == [j["canonical_key"] for j in wordy]

    def test_an_empty_query_returns_everything(self):
        assert len(keyword_filter(CORPUS, "", PREFS)) == len(CORPUS)


class TestRanking:
    def test_a_title_hit_outranks_a_description_hit(self):
        corpus = [job("A", "Data Analyst", description="no keyword here"),
                  job("B", "Something Else", description="we use python daily"),
                  job("C", "Python Engineer", description="python")]
        got = keyword_filter(corpus, "python", PREFS)
        assert got[0]["company"] == "C"

    def test_a_preferred_role_lifts_a_match_it_does_not_add_one(self):
        prefs = {"roles": ["backend"], "excluded_companies": []}
        # "microsoft" still matches nothing, and a role preference must not rescue it.
        assert keyword_filter(CORPUS, "microsoft", prefs) == []


class TestDeduplication:
    def test_the_same_opening_published_twice_appears_once(self):
        """The demo portal can publish a role repeatedly; three identical cards
        in one answer reads as broken regardless of why."""
        dupes = [job("Northwind Labs", "Cloud Engineer Intern (AWS)", description="AWS internship.",
                     source="northwind-test-portal")] * 3
        assert len(keyword_filter(dupes, "cloud", PREFS)) == 1

    def test_the_same_role_on_two_boards_appears_once(self):
        a = job("Acme", "Backend Engineer", source="greenhouse-public", key=None)
        b = job("Acme", "Backend Engineer", source="lever-public", key=None)
        assert len(keyword_filter([a, b], "backend", PREFS)) == 1

    def test_different_roles_at_one_company_are_both_kept(self):
        got = keyword_filter([job("Acme", "Backend Engineer"), job("Acme", "Frontend Engineer")], "engineer", PREFS)
        assert len(got) == 2


class TestExclusions:
    def test_an_excluded_company_never_appears(self):
        prefs = {"roles": [], "excluded_companies": ["Gitlab"]}
        assert all(j["company"] != "Gitlab" for j in keyword_filter(CORPUS, "backend", prefs))


class TestDedupeDoesNotTrustTheBoard:
    """665 Stripe postings arrived sharing one canonical_key and became 2."""

    def test_a_repeated_upstream_key_does_not_collapse_distinct_roles(self):
        corpus = [
            {**job("Stripe", "Backend Engineer"), "canonical_key": "greenhouse:stripe:See Opening ID"},
            {**job("Stripe", "Frontend Engineer"), "canonical_key": "greenhouse:stripe:See Opening ID"},
            {**job("Stripe", "Data Engineer"), "canonical_key": "greenhouse:stripe:See Opening ID"},
        ]
        assert len(keyword_filter(corpus, "engineer", PREFS)) == 3

    def test_the_same_role_still_collapses_despite_different_upstream_keys(self):
        corpus = [
            {**job("Stripe", "Backend Engineer"), "canonical_key": "greenhouse:stripe:A"},
            {**job("Stripe", "Backend Engineer"), "canonical_key": "greenhouse:stripe:B"},
        ]
        assert len(keyword_filter(corpus, "backend", PREFS)) == 1


class TestWordForms:
    """A person types "engineering"; the posting says "Engineer". Requiring the
    exact word found nothing for a company with 400 live openings."""

    AMAZON = [job("Amazon", "Software Dev Engineer", location="Bengaluru, Karnataka, IND",
                  description="Build services.", source="amazon-jobs")]

    def test_the_form_the_person_typed_does_not_have_to_match(self):
        for query in ("amazon engineering bengaluru", "amazon engineer", "amazon engineers"):
            assert len(keyword_filter(self.AMAZON, query, PREFS)) == 1, query

    def test_an_unrelated_word_still_disqualifies(self):
        for query in ("amazon marketing", "amazon nursing", "amazon accountant"):
            assert keyword_filter(self.AMAZON, query, PREFS) == [], query

    def test_it_does_not_rescue_a_company_we_do_not_cover(self):
        assert keyword_filter(self.AMAZON, "microsoft engineering", PREFS) == []


class TestSnapshotIndexing:
    """Search asks for a feed ("greenhouse:stripe"); the connector names itself
    something else ("greenhouse-public"). Indexing by the connector made every
    live board invisible to search - only the test portal matched, because its
    two names happen to be the same string."""

    def _wf(self):
        from helpers import make
        wf, _store, _clock = make()
        return wf

    def _job(self, **over):
        base = {"job_key": "greenhouse:stripe:1", "source": "greenhouse-public", "feed": "greenhouse:stripe",
                "company": "Stripe", "title": "Backend Engineer", "location": "Bengaluru",
                "description": "Build APIs.", "content_hash": "h1"}
        base.update(over)
        return base

    def test_a_new_snapshot_is_indexed_by_its_feed(self):
        from career_agent.matching import save_job_snapshot
        wf = self._wf()
        save_job_snapshot(wf, self._job())
        assert wf.store.get("JOB#greenhouse:stripe:1", "SNAPSHOT")["gsi1pk"] == "SOURCE#greenhouse:stripe"

    def test_an_old_snapshot_is_repaired_without_waiting_for_an_edit(self):
        from career_agent.matching import save_job_snapshot
        wf = self._wf()
        wf.store.put({"pk": "JOB#greenhouse:stripe:1", "sk": "SNAPSHOT", **self._job(),
                      "gsi1pk": "SOURCE#greenhouse-public", "gsi1sk": "2026-01-01"})
        save_job_snapshot(wf, self._job())  # identical content: nothing has changed
        assert wf.store.get("JOB#greenhouse:stripe:1", "SNAPSHOT")["gsi1pk"] == "SOURCE#greenhouse:stripe"

    def test_a_feedless_job_falls_back_to_its_source(self):
        from career_agent.matching import save_job_snapshot
        wf = self._wf()
        job = self._job()
        del job["feed"]
        save_job_snapshot(wf, job)
        assert wf.store.get("JOB#greenhouse:stripe:1", "SNAPSHOT")["gsi1pk"] == "SOURCE#greenhouse-public"

    def test_a_normalisation_change_reaches_existing_snapshots(self):
        """Amazon roles were stored under the hiring entity ("ASSPL - Karnataka")
        before the company name was normalised. Company is not in the content
        hash, so nothing would ever have rewritten it."""
        from career_agent.matching import save_job_snapshot
        wf = self._wf()
        old = self._job(company="ASSPL - Karnataka")
        wf.store.put({"pk": "JOB#greenhouse:stripe:1", "sk": "SNAPSHOT", **old,
                      "gsi1pk": "SOURCE#greenhouse:stripe", "gsi1sk": "2026-01-01"})
        save_job_snapshot(wf, self._job(company="Amazon"))  # same content hash
        assert wf.store.get("JOB#greenhouse:stripe:1", "SNAPSHOT")["company"] == "Amazon"


class TestAbbreviations:
    """Amazon titles every engineering role "Software Dev Engineer". A person
    types "sde", which is what Amazon itself calls the job everywhere else."""

    CORPUS = [
        job("Amazon", "Software Dev Engineer II", location="Bengaluru, IND", source="amazon-jobs"),
        job("Stripe", "Site Reliability Engineer", location="Bengaluru"),
        job("Nvidia", "Machine Learning Engineer", location="Pune", source="workday-public"),
    ]

    def test_sde_finds_software_dev_engineer(self):
        got = keyword_filter(self.CORPUS, "amazon sde", PREFS)
        assert [j["company"] for j in got] == ["Amazon"]

    def test_sre_and_ml_resolve_too(self):
        assert [j["company"] for j in keyword_filter(self.CORPUS, "sre", PREFS)] == ["Stripe"]
        assert [j["company"] for j in keyword_filter(self.CORPUS, "ml engineer", PREFS)] == ["Nvidia"]

    def test_an_alias_does_not_match_everything(self):
        assert keyword_filter(self.CORPUS, "amazon sre", PREFS) == []
        assert keyword_filter(self.CORPUS, "microsoft sde", PREFS) == []


class TestTestEmployerIsNotASearchResult:
    """A fictional company competing with real openings is what made results
    look made up. It belongs to the pipeline demo, not to a job search."""

    def test_the_portal_is_excluded_from_the_searched_sources(self):
        from career_agent.discovery import all_sources
        from career_agent.sources import portal
        searched = [s for s in all_sources() if s != portal.SOURCE]
        assert portal.SOURCE not in searched
        assert portal.SOURCE in all_sources(), "the monitor must still poll it for the demo"


class TestACompanyNameFiltersTheEmployer:
    """Asking for NVIDIA returned Stripe roles, because a Stripe posting listed
    "NVIDIA NeMo" among its requirements. True about the posting, useless as an
    answer to the question."""

    CORPUS = [
        job("Stripe", "Technical Support Engineer, Metronome", location="Dublin",
            description="PyTorch, NVIDIA NeMo and vLLM experience"),
        job("Nvidia", "Senior Software Engineer, AI Inference", location="Bengaluru", source="workday-public"),
        job("Amazon", "Software Development Engineer II", location="Bengaluru, IND", source="amazon-jobs"),
    ]

    def test_a_company_term_means_that_company(self):
        assert [j["company"] for j in keyword_filter(self.CORPUS, "nvidia engineer", PREFS)] == ["Nvidia"]

    def test_a_mention_in_a_description_is_not_a_match(self):
        got = keyword_filter(self.CORPUS, "nvidia", PREFS)
        assert "Stripe" not in [j["company"] for j in got]

    def test_a_query_with_no_company_still_searches_everything(self):
        assert len(keyword_filter(self.CORPUS, "engineer", PREFS)) == 3

    def test_two_companies_at_once_match_nothing(self):
        """No posting belongs to two employers, and pretending otherwise invents results."""
        assert keyword_filter(self.CORPUS, "nvidia stripe", PREFS) == []

    def test_a_company_plus_a_role_still_narrows(self):
        assert keyword_filter(self.CORPUS, "amazon support", PREFS) == []


class TestAPlaceNameFiltersTheLocation:
    """Asking for India returned a role in Seoul, because its description
    mentioned working with teams in India. Same mistake as the company one."""

    CORPUS = [
        job("Matchgroup", "Product Designer, International Growth", location="Seoul, South Korea",
            description="work with teams in India and Japan", source="lever-public"),
        job("Stripe", "Software Engineer, Internal Systems", location="Bengaluru, India"),
        job("Amazon", "Software Development Engineer II", location="Bengaluru, Karnataka, IND",
            source="amazon-jobs"),
        job("Nvidia", "Senior Software Engineer", location="US, CA, Santa Clara", source="workday-public"),
    ]

    def test_a_place_term_means_that_place(self):
        got = [j["company"] for j in keyword_filter(self.CORPUS, "engineer india", PREFS)]
        assert "Matchgroup" not in got
        assert set(got) == {"Stripe", "Amazon"}

    def test_a_country_spelled_differently_by_the_board_still_matches(self):
        """Amazon writes "IND", Stripe writes "India"; a person types one word."""
        assert "Amazon" in [j["company"] for j in keyword_filter(self.CORPUS, "india", PREFS)]

    def test_a_city_works_as_well_as_a_country(self):
        assert set(j["company"] for j in keyword_filter(self.CORPUS, "bengaluru", PREFS)) == {"Stripe", "Amazon"}

    def test_a_query_with_no_place_is_unaffected(self):
        assert len(keyword_filter(self.CORPUS, "designer", PREFS)) == 1

    def test_company_and_place_narrow_together(self):
        assert [j["company"] for j in keyword_filter(self.CORPUS, "amazon india", PREFS)] == ["Amazon"]
        assert keyword_filter(self.CORPUS, "nvidia india", PREFS) == []
