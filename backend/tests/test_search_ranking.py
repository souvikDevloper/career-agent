import helpers  # noqa: F401

from career_agent.services import _candidate_pool_size, _rank_match_cards


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
    assert _candidate_pool_size(100, 6) == 18
    assert _candidate_pool_size(100, 12) == 24
    assert _candidate_pool_size(4, 6) == 4
