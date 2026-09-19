"""The resume builder's model call.

It shipped calling bedrock-runtime.converse directly, which works against a mock
server and fails on the real account with "ValidationException: Operation not
allowed" - Bedrock runtime is held, and llm.py exists precisely to route to
whichever provider is configured instead. A route that reaches boto3 on its own
is therefore broken in production no matter what its tests say.
"""

from __future__ import annotations

import json

import pytest
from helpers import T0  # noqa: F401  (adds src/ to sys.path)

from career_agent import llm
from career_agent.handlers import api

USER = "11111111-2222-3333-4444-555555555555"


def event(body):
    return {
        "rawPath": "/api/resume/builder/chat",
        "requestContext": {"http": {"method": "POST"}, "requestId": "req-1",
                           "authorizer": {"jwt": {"claims": {"sub": USER, "email": "a@example.test"}}}},
        "headers": {}, "body": json.dumps(body),
    }


class FakeWorkflow:
    def __init__(self, allow=True):
        self.allow = allow

    def reserve_usage(self, *a, **k):
        return self.allow


class FakeServices:
    def __init__(self, allow=True):
        self.wf = FakeWorkflow(allow)


@pytest.fixture
def svc(monkeypatch):
    fake = FakeServices()
    monkeypatch.setattr(api, "_svc", lambda: fake)
    return fake


class TestItUsesTheConfiguredProvider:
    def test_the_reply_and_patch_come_back_from_json_call(self, svc, monkeypatch):
        monkeypatch.setattr(api.llm, "json_call",
                            lambda *a, **k: {"reply": "Added a summary.", "latex_patch": "\documentclass{article}"})
        res = api.handler(event({"message": "add a summary", "latex_context": "\documentclass{article}"}), None)
        body = json.loads(res["body"])
        assert res["statusCode"] == 200
        assert body["reply"] == "Added a summary."
        assert body["latex_patch"] == "\documentclass{article}"

    def test_it_never_reaches_boto3_itself(self, svc, monkeypatch):
        """The specific regression: a direct bedrock-runtime client bypasses the
        provider switch and is denied on this account."""
        import boto3

        def forbidden(*a, **k):
            raise AssertionError("the route built its own AWS client instead of using llm")

        monkeypatch.setattr(boto3, "client", forbidden)
        monkeypatch.setattr(api.llm, "json_call", lambda *a, **k: {"reply": "ok", "latex_patch": None})
        assert api.handler(event({"message": "hi", "latex_context": "x"}), None)["statusCode"] == 200

    def test_an_unavailable_model_is_a_service_error_not_a_crash(self, svc, monkeypatch):
        def unavailable(*a, **k):
            raise llm.ModelUnavailable("provider unreachable")

        monkeypatch.setattr(api.llm, "json_call", unavailable)
        res = api.handler(event({"message": "hi", "latex_context": "x"}), None)
        assert res["statusCode"] == 503
        assert "unavailable" in json.loads(res["body"])["error"]["message"].lower()

    def test_a_non_string_patch_is_dropped_rather_than_sent_to_the_editor(self, svc, monkeypatch):
        """The editor replaces the whole document with this value; anything that
        is not LaTeX source would wipe the resume."""
        monkeypatch.setattr(api.llm, "json_call", lambda *a, **k: {"reply": "hm", "latex_patch": {"not": "latex"}})
        assert json.loads(api.handler(event({"message": "hi", "latex_context": "x"}), None)["body"])["latex_patch"] is None

    def test_an_exhausted_quota_is_refused_before_the_model_is_called(self, monkeypatch):
        monkeypatch.setattr(api, "_svc", lambda: FakeServices(allow=False))
        monkeypatch.setattr(api.llm, "json_call",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("called despite no quota")))
        assert api.handler(event({"message": "hi", "latex_context": "x"}), None)["statusCode"] == 429
