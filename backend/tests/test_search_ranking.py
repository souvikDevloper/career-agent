import helpers  # noqa: F401

from career_agent.services import SCORING_BUDGET_SECONDS, _candidate_pool_size, _rank_match_cards


def card(key, score, blocked=False, published="2026-09-01"):
    return {"job_key": key, "score": score, "blocked": blocked,
            "job": {"published_at": published}}


def test_fit_ranking_happens_after_scoring():
    got = _rank_match_cards([
        card("retrieval-first", 61),
        card("better-fit", 91),
        card("middle", 77),
    ])
    assert [c["job_key"] for c in got] == ["better-fit", "middle", "retrieval-first"]


def test_blocked_role_does_not_beat_an_eligible_one_even_with_higher_score():
    got = _rank_match_cards([
        card("blocked", 99, blocked=True),
        card("eligible", 75, blocked=False),
    ])
    assert [c["job_key"] for c in got] == ["eligible", "blocked"]


def test_search_scores_more_than_the_requested_count_before_ranking():
    """Retrieval relevance and resume fit are different rankings, so the best fit
    often sits below a merely keyword-heavy posting. Scoring only the requested
    count means never seeing it."""
    assert _candidate_pool_size(100, 6) == 18
    assert _candidate_pool_size(100, 12) == 24, "capped, so a big request cannot run away"
    assert _candidate_pool_size(4, 6) == 4, "never score more than there are matches"
    assert _candidate_pool_size(100, 1) == 3


def test_the_pool_is_an_intention_not_a_promise():
    """The wider pool is affordable because it is bounded. Without a deadline a
    slow endpoint turns a search into a Lambda that runs out of time mid-flight
    and returns nothing at all."""
    assert SCORING_BUDGET_SECONDS > 0
    assert SCORING_BUDGET_SECONDS < 300, "must finish inside the worker's own timeout"
