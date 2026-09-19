"""Selecting a model provider.

Bedrock is the default and must stay the default: this whole layer exists only
because this AWS account cannot reach it, and the moment the hold lifts the
fallback should be one environment variable away from being switched off.

The risk worth testing is the translation. Every caller, including the agent's
tool loop, is written against Bedrock's Converse shape, so a second provider is
only safe if its responses come back in exactly that shape - and if a tool call
survives the round trip intact, because a mangled one silently runs the wrong
thing with the wrong arguments.
"""

from __future__ import annotations

import json

import pytest
from helpers import T0  # noqa: F401  (adds src/ to sys.path)

from career_agent import llm


@pytest.fixture
def as_openai(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_API_BASE", "https://models.example.test/v1")
    monkeypatch.setenv("FALLBACK_MODEL_ID", "some-fast-model")
    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_API_KEY_PARAM", "")
    monkeypatch.setattr(llm, "_api_key", None, raising=False)


def completion(text=None, tool_calls=None, finish="stop"):
    message = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5}}


class TestDefault:
    def test_bedrock_unless_asked_otherwise(self, monkeypatch):
        monkeypatch.delenv("MODEL_PROVIDER", raising=False)
        assert llm.provider() == "bedrock"

    @pytest.mark.parametrize("value", ["gemini", "ollama", "", "BEDROCK-ish", "openaiX"])
    def test_an_unknown_value_does_not_silently_switch(self, monkeypatch, value):
        """A typo in a deploy parameter must not quietly route somewhere else."""
        monkeypatch.setenv("MODEL_PROVIDER", value)
        assert llm.provider() == "bedrock"

    def test_openai_is_opt_in(self, as_openai):
        assert llm.provider() == "openai"

    def test_anthropic_is_opt_in(self, monkeypatch):
        monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
        assert llm.provider() == "anthropic"


def test_bounded_call_timeout_reaches_http_provider(as_openai, monkeypatch):
    import urllib.request
    seen = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self):
            return json.dumps(completion(text='{"ok": true}')).encode()
    def urlopen(request, *, timeout):
        seen.append(timeout)
        return Response()
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert llm.json_call("system", "question", timeout_seconds=7, repair=False) == {"ok": True}
    assert seen == [7]


class TestRequestTranslation:
    def test_system_prompt_leads(self, as_openai):
        out = llm._to_openai_messages("be truthful", [{"role": "user", "content": [{"text": "hi"}]}])
        assert out[0] == {"role": "system", "content": "be truthful"}
        assert out[1]["role"] == "user" and out[1]["content"] == "hi"

    def test_documents_become_text_not_a_file(self, as_openai):
        blocks = [{"text": "read this"}, {"document": {"name": "resume", "source": {"bytes": b"Asha Rao, Python"}}}]
        got = llm._blocks_to_text(blocks)
        assert "read this" in got and "Asha Rao, Python" in got

    def test_a_tool_result_becomes_its_own_tool_message(self, as_openai):
        messages = [{"role": "user", "content": [
            {"toolResult": {"toolUseId": "call_1", "content": [{"text": '{"matches": []}'}]}}]}]
        out = llm._to_openai_messages("", messages)
        assert out == [{"role": "tool", "tool_call_id": "call_1", "content": '{"matches": []}'}]

    def test_an_assistant_tool_use_is_carried_across(self, as_openai):
        messages = [{"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "call_9", "name": "search_jobs", "input": {"keywords": "backend"}}}]}]
        out = llm._to_openai_messages("", messages)
        call = out[0]["tool_calls"][0]
        assert call["id"] == "call_9"
        assert call["function"]["name"] == "search_jobs"
        assert json.loads(call["function"]["arguments"]) == {"keywords": "backend"}


class TestResponseTranslation:
    def test_plain_text(self):
        res = llm._to_bedrock_response(completion(text="Three roles fit you."))
        assert llm.response_text(res) == "Three roles fit you."
        assert res["stopReason"] == "end_turn"
        assert res["usage"] == {"inputTokens": 11, "outputTokens": 5}

    def test_a_tool_call_arrives_in_bedrock_shape(self):
        res = llm._to_bedrock_response(completion(
            tool_calls=[{"id": "call_2", "type": "function",
                         "function": {"name": "create_watch", "arguments": '{"keywords": "cloud intern"}'}}],
            finish="tool_calls"))
        block = res["output"]["message"]["content"][0]["toolUse"]
        assert block == {"toolUseId": "call_2", "name": "create_watch", "input": {"keywords": "cloud intern"}}
        assert res["stopReason"] == "tool_use"

    def test_unparseable_arguments_become_empty_not_a_crash(self):
        """The tool then reports a missing argument, which the model can recover from."""
        res = llm._to_bedrock_response(completion(
            tool_calls=[{"id": "c", "function": {"name": "search_jobs", "arguments": "{not json"}}],
            finish="tool_calls"))
        assert res["output"]["message"]["content"][0]["toolUse"]["input"] == {}

    def test_truncation_is_reported_the_same_way_bedrock_reports_it(self):
        assert llm._to_bedrock_response(completion(text="cut off", finish="length"))["stopReason"] == "max_tokens"

    def test_an_empty_reply_still_has_the_expected_shape(self):
        res = llm._to_bedrock_response(completion(text=None))
        assert res["output"]["message"]["content"] == [{"text": ""}]
        assert llm.response_text(res) == ""


class TestRoundTrip:
    def test_a_tool_call_survives_going_out_and_coming_back(self, as_openai):
        """The dangerous failure is a call that runs with the wrong arguments."""
        original = {"toolUse": {"toolUseId": "call_7", "name": "update_preferences",
                                "input": {"roles": ["backend"], "min_salary": 600000}}}
        outbound = llm._to_openai_messages("", [{"role": "assistant", "content": [original]}])
        call = outbound[0]["tool_calls"][0]
        back = llm._to_bedrock_response(completion(tool_calls=[call], finish="tool_calls"))
        assert back["output"]["message"]["content"][0]["toolUse"] == original["toolUse"]


class TestFailuresAreReportedAsUnavailable:
    """Callers catch ModelUnavailable and degrade honestly; anything else is a 500."""

    def test_a_missing_key(self, monkeypatch):
        monkeypatch.setenv("MODEL_PROVIDER", "openai")
        monkeypatch.setenv("MODEL_API_KEY", "")
        monkeypatch.setenv("MODEL_API_KEY_PARAM", "")
        monkeypatch.setattr(llm, "_api_key", None, raising=False)
        with pytest.raises(llm.ModelUnavailable):
            llm.openai_key()

    def test_a_provider_error(self, as_openai, monkeypatch):
        def boom(*a, **k):
            raise OSError("connection reset")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        with pytest.raises(llm.ModelUnavailable):
            llm._openai_chat("", [{"role": "user", "content": [{"text": "hi"}]}], None, 10, 0.2)

    def test_a_provider_failure_counts_as_unavailable(self, as_openai):
        assert llm.is_unavailable(llm.ModelUnavailable("model provider returned 429"))


class TestAnthropicRoute:
    """The Bedrock mantle endpoint routes by model: Anthropic models answer on
    /v1/messages and refuse /v1/chat/completions, so the wire format follows the
    model rather than the other way round."""

    def test_converse_blocks_become_anthropic_blocks(self):
        got = llm._to_anthropic("be truthful", [{"role": "user", "content": [{"text": "hi"}]}])
        assert got["system"] == "be truthful"
        assert got["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    def test_a_tool_use_is_renamed_not_rewritten(self):
        got = llm._to_anthropic("", [{"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t1", "name": "search_jobs", "input": {"keywords": "backend"}}}]}])
        assert got["messages"][0]["content"][0] == {
            "type": "tool_use", "id": "t1", "name": "search_jobs", "input": {"keywords": "backend"}}

    def test_a_tool_result_carries_its_id(self):
        got = llm._to_anthropic("", [{"role": "user", "content": [
            {"toolResult": {"toolUseId": "t1", "content": [{"text": "{}"}]}}]}])
        assert got["messages"][0]["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "{}"}

    def test_a_reply_comes_back_in_converse_shape(self):
        res = llm._from_anthropic({"content": [{"type": "text", "text": "Two roles fit you."}],
                                   "stop_reason": "end_turn",
                                   "usage": {"input_tokens": 9, "output_tokens": 4}})
        assert llm.response_text(res) == "Two roles fit you."
        assert res["usage"] == {"inputTokens": 9, "outputTokens": 4}

    def test_a_tool_call_comes_back_in_converse_shape(self):
        res = llm._from_anthropic({"content": [
            {"type": "tool_use", "id": "t9", "name": "create_watch", "input": {"keywords": "cloud"}}],
            "stop_reason": "tool_use"})
        assert res["stopReason"] == "tool_use"
        assert res["output"]["message"]["content"][0]["toolUse"] == {
            "toolUseId": "t9", "name": "create_watch", "input": {"keywords": "cloud"}}

    def test_truncation_maps_across(self):
        assert llm._from_anthropic({"content": [{"type": "text", "text": "cut"}],
                                    "stop_reason": "max_tokens"})["stopReason"] == "max_tokens"

    def test_round_trip_keeps_a_tool_call_intact(self):
        original = {"toolUse": {"toolUseId": "t7", "name": "update_preferences",
                                "input": {"roles": ["backend"], "min_salary": 600000}}}
        out = llm._to_anthropic("", [{"role": "assistant", "content": [original]}])
        block = out["messages"][0]["content"][0]
        back = llm._from_anthropic({"content": [block], "stop_reason": "tool_use"})
        assert back["output"]["message"]["content"][0]["toolUse"] == original["toolUse"]
