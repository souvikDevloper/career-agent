"""The MCP connector.

Two things are being protected here. The protocol has to be right enough that a
real client completes a handshake and reads the tool list, and the identity
rules have to hold on this door exactly as they do on every other one: the owner
comes from the validated JWT, and approving a submission is not reachable.
"""

from __future__ import annotations

import json

import pytest
from helpers import T0  # noqa: F401  (adds src/ to sys.path)

from career_agent import mcp
from career_agent.handlers import api

# --------------------------------------------------------------------------- protocol


def call(method, params=None, msg_id=1, tool_runner=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        msg["id"] = msg_id
    if params is not None:
        msg["params"] = params
    return mcp.dispatch(msg, tool_runner or (lambda name, args: {"ok": True}))


class TestHandshake:
    def test_initialize_reports_tools_and_identity(self):
        res = call("initialize", {"protocolVersion": "2025-06-18"})["result"]
        assert res["protocolVersion"] == "2025-06-18"
        assert res["capabilities"]["tools"] == {"listChanged": False}
        assert res["serverInfo"]["name"] == "career-agent"
        assert "approve" in res["instructions"].lower()

    def test_unknown_version_gets_our_newest_not_an_error(self):
        res = call("initialize", {"protocolVersion": "1999-01-01"})["result"]
        assert res["protocolVersion"] == mcp.SUPPORTED_VERSIONS[0]

    def test_older_supported_version_is_honoured(self):
        got = call("initialize", {"protocolVersion": "2024-11-05"})["result"]
        assert got["protocolVersion"] == "2024-11-05"

    def test_initialized_notification_gets_no_reply(self):
        """A reply to a notification is a protocol violation, not just noise."""
        assert call("notifications/initialized", msg_id=None) is None

    def test_ping(self):
        assert call("ping")["result"] == {}

    @pytest.mark.parametrize("method", ["resources/list", "prompts/list"])
    def test_probed_capabilities_answer_empty_rather_than_erroring(self, method):
        assert "error" not in call(method)

    def test_unknown_method_is_a_jsonrpc_error(self):
        assert call("tools/subscribe")["error"]["code"] == mcp.METHOD_NOT_FOUND

    def test_non_jsonrpc_message_is_rejected(self):
        assert mcp.dispatch({"method": "ping"}, None)["error"]["code"] == mcp.INVALID_REQUEST
        assert mcp.dispatch("ping", None)["error"]["code"] == mcp.INVALID_REQUEST


class TestToolList:
    def test_every_tool_is_usable_without_reading_our_source(self):
        for tool in mcp.tool_list():
            assert tool["description"], tool["name"] + " has no description"
            assert tool["inputSchema"]["type"] == "object"
            for pname, prop in tool["inputSchema"]["properties"].items():
                assert "type" in prop, tool["name"] + "." + pname + " has no type"

    def test_list_types_survive_the_schema_builder(self):
        prefs = next(t for t in mcp.tool_list() if t["name"] == "update_preferences")
        roles = prefs["inputSchema"]["properties"]["roles"]
        assert roles["type"] == "array" and roles["items"]["type"] == "string"
        assert prefs["inputSchema"]["properties"]["min_salary"]["type"] == "integer"

    def test_required_matches_the_signature(self):
        """search_jobs takes structured filters, all optional - an empty search is
        a valid request meaning "show me anything"."""
        search = next(t for t in mcp.tool_list() if t["name"] == "search_jobs")
        assert search["inputSchema"]["required"] == []
        props = search["inputSchema"]["properties"]
        assert {"role", "company", "location", "min_score"} <= set(props)
        assert props["min_score"]["type"] == "integer"

    def test_a_tool_that_does_take_a_required_argument_says_so(self):
        watch = next(t for t in mcp.tool_list() if t["name"] == "create_watch")
        assert watch["inputSchema"]["required"] == ["keywords"]


class TestApprovalIsNotReachable:
    """Submitting is the one irreversible act; a tool call cannot evidence consent."""

    def test_it_is_absent_from_the_advertised_surface(self):
        assert "approve_application" not in [t["name"] for t in mcp.tool_list()]

    def test_calling_it_anyway_explains_where_to_go(self):
        ran = []
        res = call("tools/call", {"name": "approve_application", "arguments": {}},
                   tool_runner=lambda n, a: ran.append(n))["result"]
        assert res["isError"] is True
        assert "app" in res["content"][0]["text"].lower()
        assert ran == [], "the withheld tool was executed"


class TestToolCall:
    def test_success_carries_both_text_and_structured_output(self):
        res = call("tools/call", {"name": "list_matches", "arguments": {}},
                   tool_runner=lambda n, a: {"matches": [{"score": 91}]})["result"]
        assert res["isError"] is False
        assert json.loads(res["content"][0]["text"]) == {"matches": [{"score": 91}]}
        assert res["structuredContent"] == {"matches": [{"score": 91}]}

    def test_unknown_tool_is_a_params_error(self):
        assert call("tools/call", {"name": "rm_rf", "arguments": {}})["error"]["code"] == mcp.INVALID_PARAMS

    def test_a_failing_tool_is_reported_to_the_model_not_raised(self):
        """isError lets the caller's model read the failure and try something else."""

        def boom(name, args):
            raise RuntimeError("Bedrock is unavailable")

        res = call("tools/call", {"name": "search_jobs", "arguments": {"keywords": "x"}}, tool_runner=boom)["result"]
        assert res["isError"] is True
        assert "Bedrock is unavailable" in res["content"][0]["text"]

    def test_bad_arguments_are_reported_the_same_way(self):
        def strict(name, args):
            raise TypeError("unexpected keyword argument 'user_id'")

        res = call("tools/call", {"name": "list_matches", "arguments": {"user_id": "someone-else"}},
                   tool_runner=strict)["result"]
        assert res["isError"] is True
        assert "Invalid arguments" in res["content"][0]["text"]

    def test_missing_arguments_object_is_treated_as_empty(self):
        assert call("tools/call", {"name": "list_matches"})["result"]["isError"] is False


# --------------------------------------------------------------------------- the HTTP door


class FakeWorkflow:
    def __init__(self):
        self.seen_uids = []
        self.operations = 0

    def settings(self, uid):
        self.seen_uids.append(uid)
        return {"preferences": {"roles": ["backend"]}, "mode": "review", "daily_cap": 5}

    def list_apps(self, uid):
        self.seen_uids.append(uid)
        return [{"app_id": "app_1", "title": "Backend Intern", "company": "Northwind Labs", "score": 88,
                 "action_state": "NeedsApproval", "recruitment_stage": "Applied", "target_environment": "test"}]

    def start_operation(self, uid, kind, payload, client_request_id, correlation_id):
        self.operations += 1
        return {"op_id": "op_fake"}, True


class FakeProfiles:
    def current(self, uid):
        return {"facts": {"name": "Asha Rao", "headline": "Final-year CS", "skills": [{"name": "Python"}],
                          "education": [], "projects": []}}


class FakeServices:
    def __init__(self):
        self.wf = FakeWorkflow()
        self.profiles = FakeProfiles()


USER = "11111111-2222-3333-4444-555555555555"


def event(body, sub=USER):
    return {
        "rawPath": "/api/mcp",
        "requestContext": {"http": {"method": "POST"}, "requestId": "req-abc-123",
                           "authorizer": {"jwt": {"claims": {"sub": sub, "email": "asha@example.test"}}}},
        "headers": {},
        "body": body if isinstance(body, str) else json.dumps(body),
    }


@pytest.fixture
def svc(monkeypatch):
    fake = FakeServices()
    monkeypatch.setattr(api, "_svc", lambda: fake)
    return fake


class TestHttpDoor:
    def test_unauthenticated_requests_never_reach_the_protocol(self):
        ev = event({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        ev["requestContext"]["authorizer"] = {}
        assert api.handler(ev, None)["statusCode"] == 401

    def test_tools_list_over_http(self, svc):
        res = api.handler(event({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}), None)
        assert res["statusCode"] == 200
        names = [t["name"] for t in json.loads(res["body"])["result"]["tools"]]
        assert "search_jobs" in names and "approve_application" not in names

    def test_a_notification_is_acknowledged_with_no_body(self, svc):
        res = api.handler(event({"jsonrpc": "2.0", "method": "notifications/initialized"}), None)
        assert res["statusCode"] == 202
        assert res["body"] == ""

    def test_the_tool_runs_as_the_jwt_subject(self, svc):
        res = api.handler(event({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                 "params": {"name": "list_applications", "arguments": {}}}), None)
        result = json.loads(res["body"])["result"]
        assert result["isError"] is False, result["content"][0]["text"]
        assert result["structuredContent"]["applications"][0]["app_id"] == "app_1"
        assert svc.wf.seen_uids == [USER]

    def test_the_body_cannot_name_a_different_owner(self, svc):
        """user_id is not a parameter of any tool, so naming one is rejected outright."""
        res = api.handler(event({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"name": "list_applications",
                                            "arguments": {"user_id": "victim", "state": "NeedsApproval"}}}), None)
        result = json.loads(res["body"])["result"]
        assert result["isError"] is True
        assert "victim" not in json.dumps(svc.wf.seen_uids)

    def test_malformed_json_is_a_parse_error_not_a_500(self, svc):
        res = api.handler(event("{not json"), None)
        assert res["statusCode"] == 200
        assert json.loads(res["body"])["error"]["code"] == mcp.PARSE_ERROR

    def test_no_operation_is_written_for_a_read(self, svc):
        """start_operation is a DynamoDB write; read-only calls must not pay for one."""
        api.handler(event({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "profile_summary", "arguments": {}}}), None)
        assert svc.wf.operations == 0
