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
