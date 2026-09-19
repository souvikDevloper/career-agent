"""Source failures, authoritative results and cached results are distinct states."""

from types import SimpleNamespace

import helpers  # noqa: F401
import pytest

from career_agent import agent, discovery, services
from career_agent.services import Services
from career_agent.sources import google, microsoft, workday
from career_agent.sources.http import FetchError


def job(key, title="Software Engineer", company="Google"):
    return {"job_key": key, "title": title, "company": company, "location": "Bengaluru, India",
            "description": "Build products", "source": "google-careers", "feed": "google:direct"}


@pytest.fixture
def search_service(monkeypatch):
    wf, store, clock = helpers.make()
    svc = Services(store, clock)
    monkeypatch.setenv("ENABLE_TEST_EMPLOYER", "false")
    monkeypatch.setattr(svc.profiles, "current", lambda uid: {"facts": {}})
    monkeypatch.setattr(svc.wf, "op_progress", lambda *a, **k: None)
    monkeypatch.setattr(discovery, "all_sources", lambda: ["cached"])
    monkeypatch.setattr(discovery, "save_job_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(discovery, "cached_jobs", lambda wf, source: [
        job("old", "Staff Software Engineer"), job("old-stripe", company="Stripe")] if source == "cached" else [])
    monkeypatch.setattr(svc.matcher, "match", lambda uid, j, **k: {
        "job_key": j["job_key"], "job": j, "score": 80, "blocked": False, "unknowns": []})
    return svc


def search(svc, stats):
    return svc.search("u1", "op1", filters={"company": "Google", "role": "SWE early career", "location": "India"}, stats=stats)


def test_successful_direct_search_replaces_cached_senior_roles(search_service, monkeypatch):
    monkeypatch.setattr(google, "search", lambda *a, **k: [job("fresh", "Software Engineer II")])
    stats = {}
    result = search(search_service, stats)
    assert [c["job_key"] for c in result] == ["fresh"]
    assert stats["live_postings"] == 1
    assert stats["cached_postings"] == 2
    assert stats["searched_postings"] == 1
    assert stats["freshness"] == "live"


def test_google_query_includes_youtube_without_relabeling_the_employer(search_service, monkeypatch):
    youtube = job("yt", "Software Engineer II, YouTube", company="YouTube")
    youtube["company_aliases"] = ["Google"]
    monkeypatch.setattr(google, "search", lambda *a, **k: [youtube])
    stats = {}
    results = search(search_service, stats)
    assert results[0]["job"]["company"] == "YouTube"
    assert stats["searched_postings"] == 1


def test_successful_empty_query_does_not_resurrect_a_cached_role(search_service, monkeypatch):
    monkeypatch.setattr(google, "search", lambda *a, **k: [])
    stats = {}
    assert search(search_service, stats) == []
    assert stats["source_checks"]["status"] == "succeeded"
    assert stats["matched"] == 0
    assert stats["searched_postings"] == 0


def test_failure_cannot_be_reported_as_a_successful_zero_result_search(search_service, monkeypatch):
    def fail(*a, **k):
        raise FetchError("HTTP 503")
    monkeypatch.setattr(google, "search", fail)
    stats = {}
    assert search(search_service, stats) == []
    assert stats["freshness"] == "stale_fallback"
    assert stats["source_checks"]["failed_sources"] == [{"source": "google:direct", "error": "HTTP 503"}]
    assert stats["company_covered"] is True


def test_timeout_is_also_a_source_failure(search_service, monkeypatch):
    def fail(*a, **k):
        raise TimeoutError("timed out")
    monkeypatch.setattr(google, "search", fail)
    stats = {}
    search(search_service, stats)
    assert stats["source_checks"]["status"] == "failed"


@pytest.mark.parametrize("html", ["<html>blocked</html>",
    "AF_initDataCallback({key: 'ds:1', data: [[bad]]});",
    "AF_initDataCallback({key: 'ds:1', data: [[",
    "AF_initDataCallback({key: 'ds:1', data: [42]});"])
def test_google_parser_failures_are_not_empty_searches(html):
    with pytest.raises(FetchError):
        google._extract(html)


def test_google_valid_empty_results_are_still_empty():
    assert google._extract("AF_initDataCallback({key: 'ds:1', data: [null, null, 0, 20]});") == []


def test_workday_reads_beyond_first_page_before_local_location_filter(monkeypatch):
    import json
    offsets = []
    def fetch(url, hosts, **kwargs):
        offset = json.loads(kwargs["body"])["offset"]
        offsets.append(offset)
        return {"jobPostings": [{"title": "Software Engineer", "externalPath": f"/job/{i}",
                                 "bulletFields": [str(i)], "locationsText": "India" if i == 20 else "USA"}
                                for i in range(offset, min(21, offset + 20))]}
    monkeypatch.setattr(workday, "fetch_json", fetch)
    jobs = workday.search("adobe:wd5:external", "software engineer", limit=100)
    assert offsets == [0, 20]
    assert [j["external_id"] for j in discovery.filter_jobs(jobs, {}, location="India")] == ["20"]


def test_empty_search_reply_cannot_repeat_unrelated_history():
    context = agent.ToolContext("u", "op", "Google SWE India", "chat", "cid", object())
    context.actions = [{"type": "search", "count": 0}]
    context.search_result = {"results": [], "searched": {
        "filters": {"company": "Google", "role": "SWE", "location": "India"},
        "matched": 0, "freshness": "live", "searched_postings": 0, "company_covered": True}}
    reply = agent._ground_search_reply(context, "Apply to Amazon or Stripe instead.")
    assert "Google" in reply
    assert "Amazon" not in reply and "Stripe" not in reply


def test_matches_tool_keeps_the_current_search_scope():
    svc = SimpleNamespace(matcher=SimpleNamespace(list=lambda uid: [
        {"job_key": "stripe", "job": job("stripe", company="Stripe"), "score": 90},
        {"job_key": "google", "job": job("google"), "score": 80}]))
    context = agent.ToolContext("u", "op", "Google SWE India", "chat", "cid", svc)
    context.search_result = {"results": [], "searched": {"filters": {"company": "Google"}}}
    agent.CTX.current = context
    try:
        result = agent.t_list_matches()
    finally:
        agent.CTX.current = None
    assert [m["job_key"] for m in result["matches"]] == ["google"]


def test_microsoft_passes_browser_headers_seniority_facet_and_pages(monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    requests = []
    def fetch(url, hosts, **kwargs):
        params = parse_qs(urlsplit(url).query)
        requests.append(params)
        assert "Mozilla/5.0" in kwargs["headers"]["User-Agent"]
        assert params["query"] == ["software engineer"]
        assert params["filter_seniority"] == ["Entry"]
        start = int(params["start"][0])
        return {"data": {"count": 11, "positions": [
            {"id": i, "name": "Software Engineer II", "locations": ["Hyderabad, India"]}
            for i in range(start + 1, min(start + 11, 12))]}}
    monkeypatch.setattr(microsoft, "fetch_json", fetch)
    jobs = microsoft.search("SWE early-career roles", location="India", limit=20)
    assert len(jobs) == 11
    assert [r["start"] for r in requests] == [["0"], ["10"]]


def test_microsoft_invalid_response_is_not_no_openings(monkeypatch):
    monkeypatch.setattr(microsoft, "fetch_json", lambda *a, **k: {"error": "blocked"})
    with pytest.raises(FetchError):
        microsoft.search("SWE")


def test_search_stops_scheduling_model_calls_at_deadline(search_service, monkeypatch):
    from threading import Lock
    monkeypatch.setattr(google, "search", lambda *a, **k: [job(str(i), f"Software Engineer, Team {i}") for i in range(12)])
    ticks = [0]
    seen = []
    guard = Lock()
    monkeypatch.setattr(services.time, "monotonic", lambda: ticks[0])
    def match(uid, item, **kwargs):
        with guard:
            seen.append(kwargs["timeout_seconds"])
            ticks[0] += 60
        return {"job_key": item["job_key"], "job": item, "score": 70, "unknowns": []}
    monkeypatch.setattr(search_service.matcher, "match", match)
    result = search(search_service, {})
    assert len(result) == 3
    assert seen == [services.SCORING_CALL_TIMEOUT_SECONDS] * 3
