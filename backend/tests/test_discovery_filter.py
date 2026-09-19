"""Which openings a search is allowed to return.

The filter used to be an OR: one matching word qualified a job. So "microsoft
internship" matched every posting containing the word "internship", and a search
for a company this product does not cover came back full of confident results
from a company the person never asked about. That is worse than an empty
result - it reads as a product that makes things up.
"""

from __future__ import annotations

from helpers import T0  # noqa: F401  (adds src/ to sys.path)

import pytest

from career_agent import discovery
from career_agent.discovery import _names_match, filter_jobs, keyword_filter

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


class TestTestEmployerIsOff:
    """A fictional company competing with real openings is what made results look
    invented. It is off unless a deploy parameter turns it on for the submission
    demo, which is the one place a real browser submission can honestly be shown."""

    def test_it_is_absent_by_default(self, monkeypatch):
        from career_agent.discovery import all_sources
        from career_agent.sources import portal
        monkeypatch.delenv("ENABLE_TEST_EMPLOYER", raising=False)
        assert portal.SOURCE not in all_sources()

    def test_it_can_be_turned_on_for_the_demo(self, monkeypatch):
        from career_agent.discovery import all_sources
        from career_agent.sources import portal
        monkeypatch.setenv("ENABLE_TEST_EMPLOYER", "true")
        assert portal.SOURCE in all_sources()

    def test_a_typo_does_not_turn_it_on(self, monkeypatch):
        from career_agent.discovery import all_sources
        from career_agent.sources import portal
        for value in ("1", "yes", "True ", ""):
            monkeypatch.setenv("ENABLE_TEST_EMPLOYER", value)
            assert portal.SOURCE not in all_sources(), value


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


class TestStructuredFilters:
    """The agent passes the parts of a request separately instead of one phrase
    the backend has to interpret. Every earlier bug in this file came from
    guessing which field a word belonged to."""

    CORPUS = [
        job("Nvidia", "Senior Software Engineer, AI Inference", location="US, CA, Santa Clara",
            source="workday-public"),
        job("Nvidia", "Systems Engineer", location="Bengaluru, India", source="workday-public"),
        job("Stripe", "Technical Support Engineer", location="Dublin",
            description="PyTorch, NVIDIA NeMo and vLLM experience"),
        job("Amazon", "Software Development Engineer II", location="Bengaluru, Karnataka, IND",
            source="amazon-jobs"),
        job("Amazon", "Financial Analyst Intern", location="Bengaluru, Karnataka, IND", source="amazon-jobs"),
    ]

    def filt(self, **kw):
        return [(j["company"], j["title"]) for j in filter_jobs(self.CORPUS, PREFS, **kw)]

    def test_company_restricts_to_that_employer(self):
        assert all(c == "Nvidia" for c, _ in self.filt(company="Nvidia"))

    def test_a_mention_in_another_posting_is_not_the_company(self):
        assert "Stripe" not in [c for c, _ in self.filt(company="Nvidia")]

    def test_company_and_location_together(self):
        assert self.filt(company="Nvidia", location="India") == [("Nvidia", "Systems Engineer")]

    def test_location_spans_the_spellings_boards_use(self):
        got = {c for c, _ in self.filt(location="India")}
        assert got == {"Nvidia", "Amazon"}

    def test_role_searches_only_the_work(self):
        assert self.filt(company="Amazon", role="intern") == [("Amazon", "Financial Analyst Intern")]

    def test_an_abbreviation_still_resolves(self):
        assert self.filt(company="Amazon", role="sde") == [("Amazon", "Software Development Engineer II")]

    def test_empty_filters_return_everything(self):
        assert len(filter_jobs(self.CORPUS, PREFS)) == len(self.CORPUS)

    def test_a_company_we_do_not_carry_returns_nothing(self):
        assert self.filt(company="Microsoft") == []

    def test_punctuation_in_the_employer_name_does_not_matter(self):
        corpus = [job("Match Group", "Product Designer", location="Seoul")]
        assert len(filter_jobs(corpus, PREFS, company="matchgroup")) == 1
        assert len(filter_jobs(corpus, PREFS, company="Match Group")) == 1

    def test_work_mode_is_an_exact_filter(self):
        corpus = [{**job("Acme", "Engineer"), "work_mode": "remote"},
                  {**job("Acme", "Engineer Two"), "work_mode": "onsite"}]
        assert len(filter_jobs(corpus, PREFS, work_mode="remote")) == 1

    def test_employment_type_is_an_exact_filter(self):
        corpus = [{**job("Acme", "Intern Role"), "employment_type": "internship"},
                  {**job("Acme", "Staff Role"), "employment_type": None}]
        assert len(filter_jobs(corpus, PREFS, employment_type="internship")) == 1

    def test_excluded_companies_still_win(self):
        prefs = {"roles": [], "excluded_companies": ["Nvidia"]}
        assert filter_jobs(self.CORPUS, prefs, company="Nvidia") == []


class TestWordBoundaries:
    """Substring matching made "intern" match "Internal Audit", so a search for
    an internship returned a Senior Manager role."""

    CORPUS = [
        job("Gitlab", "Senior Manager, Internal Audit", location="Bangalore, India"),
        job("Stripe", "Software Engineer, Internal Systems", location="Bengaluru, India"),
        job("Twilio", "Software Engineer Intern", location="Remote - India"),
        job("Rubrik", "Backend Engineering Internship", location="Bangalore"),
    ]

    def test_intern_does_not_match_internal(self):
        got = [j["company"] for j in filter_jobs(self.CORPUS, PREFS, role="intern")]
        assert set(got) == {"Twilio", "Rubrik"}

    def test_a_word_still_matches_its_own_endings(self):
        assert {j["company"] for j in filter_jobs(self.CORPUS, PREFS, role="engineering")} == {
            "Stripe", "Twilio", "Rubrik"}

    def test_intern_and_internship_are_the_same_request(self):
        """Boards title it both ways; a person types one of them."""
        both = {"Twilio", "Rubrik"}
        assert {j["company"] for j in filter_jobs(self.CORPUS, PREFS, role="internship")} == both
        assert {j["company"] for j in filter_jobs(self.CORPUS, PREFS, role="intern")} == both

    def test_a_narrow_role_stays_narrow(self):
        got = [j["company"] for j in filter_jobs(self.CORPUS, PREFS, role="backend intern")]
        assert got == ["Rubrik"]


class TestPlacesAreEquivalenceClasses:
    """A city spelled two ways is one city.

    Amazon writes "Bengaluru, Karnataka, IND" and the people who search for it
    type "Bangalore". The first version of this table only mapped country to
    city, so "india" worked and "bangalore" matched nothing at all - 204 live
    Amazon openings were invisible to anyone using the spelling they actually
    use, and the agent reported them as not existing.
    """

    CORPUS = [
        job("Amazon", "Software Development Engineer", location="Bengaluru, Karnataka, IND"),
        job("Amazon", "Software Development Engineer II", location="Hyderabad, Telangana, IND"),
        job("Amazon", "Software Development Engineer", location="Gurugram, Haryana, IND"),
        job("Nvidia", "Software Engineer", location="Windsor, Ontario"),
        job("Twilio", "Software Engineer", location="Remote - India"),
    ]

    def where(self, location):
        return [j["location"] for j in filter_jobs(self.CORPUS, PREFS, location=location)]

    def test_the_spelling_a_person_types_finds_the_spelling_the_board_uses(self):
        assert self.where("bangalore") == ["Bengaluru, Karnataka, IND"]
        assert self.where("bengaluru") == ["Bengaluru, Karnataka, IND"]
        assert self.where("gurgaon") == ["Gurugram, Haryana, IND"]

    def test_a_country_matches_its_cities_however_they_are_written(self):
        assert len(self.where("india")) == 4  # three IND cities plus "Remote - India"

    def test_a_city_does_not_widen_to_its_country(self):
        """Asking for Bengaluru is not asking for Hyderabad."""
        assert self.where("bangalore") == ["Bengaluru, Karnataka, IND"]

    def test_a_place_is_a_whole_word(self):
        """As a substring "ind" sits inside "Windsor", so searching India used to
        return jobs in Ontario."""
        assert "Windsor, Ontario" not in self.where("india")


class TestSeniorityLevel:
    """"SDE 2" names a level, and someone asking for one does not want the other."""

    CORPUS = [
        job("Amazon", "Software Development Engineer"),
        job("Amazon", "Software Development Engineer II"),
        job("Amazon", "Software Dev Engineer-II, Infra"),
        job("Amazon", "Software Development Engineer III, HST"),
    ]

    def titles(self, role):
        return [j["title"] for j in filter_jobs(self.CORPUS, PREFS, role=role)]

    def test_a_level_excludes_the_other_levels(self):
        assert self.titles("sde 2") == ["Software Development Engineer II", "Software Dev Engineer-II, Infra"]
        assert self.titles("sde ii") == ["Software Development Engineer II", "Software Dev Engineer-II, Infra"]
        assert self.titles("sde 3") == ["Software Development Engineer III, HST"]

    def test_an_unnumbered_title_is_level_one(self):
        """Amazon writes SDE I as "Software Development Engineer" with no numeral."""
        assert self.titles("sde 1") == ["Software Development Engineer"]

    def test_no_level_asked_means_every_level(self):
        assert len(self.titles("sde")) == 4

    def test_a_bare_numeral_is_not_a_seniority_filter(self):
        assert len(filter_jobs(self.CORPUS, PREFS, role="2")) == 4


class TestLiveSearchAsksOnlyTheEmployerNamed:
    """Boards too large to mirror get asked directly, and only the right one.

    Workday caps a page at 20 while a tenant like HPE publishes over 1,200 roles,
    so polling holds a slice of each - the same truncation that hid live Amazon
    postings behind the four hundred most recent.
    """

    def test_a_short_name_does_not_match_a_different_company(self):
        """"hp" and the Workday tenant "hpe" are different companies."""
        assert _names_match("hp", "hpe") is False
        assert _names_match("hpe", "hpe") is True

    def test_an_exact_name_always_matches(self):
        for name in ("amazon", "intel", "nvidia", "mastercard"):
            assert _names_match(name, name) is True

    def test_unrelated_employers_never_match(self):
        assert _names_match("google", "amazon") is False
        assert _names_match("stripe", "intel") is False

    def test_a_longer_name_may_contain_the_board_name(self):
        assert _names_match("mastercard inc", "mastercard") is True


class TestLiveSearchRuns:
    """Exercise the whole function, not just its name matching.

    This shipped broken: the structured logger takes (logger, event, **fields)
    and it was called with a level as a third positional argument, so every live
    search raised TypeError the moment it succeeded in fetching anything. The
    agent reported "a technical error" for Amazon and answered with GitLab roles
    instead. Nothing caught it because nothing called live_search.
    """

    class Store:
        def __init__(self):
            self.saved = []

        def get(self, *a, **k):
            return None

        def update(self, *a, **k):
            pass

        def put(self, item, *a, **k):
            self.saved.append(item)

        def transact(self, *a, **k):
            pass

    class Clock:
        def now(self):
            return 0.0

        def iso(self):
            return "2026-09-19T00:00:00Z"

    def wf(self):
        holder = type("WF", (), {})()
        holder.store = self.Store()
        holder.clock = self.Clock()
        return holder

    @pytest.fixture(autouse=True)
    def boards(self, monkeypatch):
        monkeypatch.setattr(discovery, "cfg", lambda: type("S", (), {
            "amazon_boards": ("IND",), "workday_boards": ("intel:wd1:External",)})())
        monkeypatch.setattr(discovery, "save_job_snapshot", lambda wf, job: (True, False))

    def test_it_returns_what_the_employer_answered(self, monkeypatch):
        monkeypatch.setattr(discovery.amazon, "search",
                            lambda country, query, limit=100: [{"job_key": "a1", "title": "SDE-1 (FTC)"}])
        got = discovery.live_search(self.wf(), company="amazon", role="sde 1")
        assert [j["title"] for j in got] == ["SDE-1 (FTC)"]

    def test_every_result_is_tagged_with_the_feed_that_produced_it(self, monkeypatch):
        """Without this the snapshot lands under the wrong index and the job
        becomes unfindable by the very search that just returned it."""
        monkeypatch.setattr(discovery.amazon, "search",
                            lambda country, query, limit=100: [{"job_key": "a1", "title": "SDE-1"}])
        assert discovery.live_search(self.wf(), company="amazon")[0]["feed"] == "amazon:IND"

    def test_a_workday_tenant_is_asked_when_it_is_named(self, monkeypatch):
        monkeypatch.setattr(discovery.workday, "search",
                            lambda spec, query, limit=20: [{"job_key": "w1", "title": "Module Engineer"}])
        got = discovery.live_search(self.wf(), company="intel", role="engineer")
        assert [j["feed"] for j in got] == ["workday:intel:wd1:External"]

    def test_an_employer_we_do_not_read_asks_nobody(self, monkeypatch):
        called = []
        monkeypatch.setattr(discovery.amazon, "search", lambda *a, **k: called.append("amazon") or [])
        monkeypatch.setattr(discovery.workday, "search", lambda *a, **k: called.append("workday") or [])
        assert discovery.live_search(self.wf(), company="google", role="engineer") == []
        assert called == []

    def test_one_board_failing_does_not_lose_the_other(self, monkeypatch):
        def boom(*a, **k):
            raise discovery.FetchError("HTTP 503")

        monkeypatch.setattr(discovery.amazon, "search", boom)
        monkeypatch.setattr(discovery.workday, "search",
                            lambda spec, query, limit=20: [{"job_key": "w1", "title": "Engineer"}])
        got = discovery.live_search(self.wf(), company="intel")
        assert [j["title"] for j in got] == ["Engineer"]

    def test_no_company_named_asks_nobody(self, monkeypatch):
        monkeypatch.setattr(discovery.amazon, "search", lambda *a, **k: [{"job_key": "x"}])
        assert discovery.live_search(self.wf(), company="", role="engineer") == []
