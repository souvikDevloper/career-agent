"""Choosing a runtime for a turn.

The agent prefers Strands and keeps its own Bedrock Converse tool loop as a
fallback. When that fallback is allowed to run is a correctness question, not a
preference: retrying a turn re-runs the turn, and some of these tools create
watches and application packets.
"""

from __future__ import annotations

import pytest
from helpers import T0  # noqa: F401  (adds src/ to sys.path)

from career_agent import agent
from career_agent.llm import ModelUnavailable


def ctx(**over):
    base = dict(user_id="u1", op_id="op_1", user_text="find me internships", channel="chat",
                correlation_id="cid-1", services=object())
    base.update(over)
    return agent.ToolContext(**base)


@pytest.fixture
def runtimes(monkeypatch):
    """Replace both runtimes so the choice between them is what is under test."""
    calls = {"strands": 0, "converse": 0}
    state: dict = {"strands_raises": None}

    def fake_strands(history):
        calls["strands"] += 1
        if state["strands_raises"]:
            raise state["strands_raises"]
        return lambda text: type("R", (), {"message": {"content": [{"text": "from strands"}]}})()

    def fake_converse(c, history):
        calls["converse"] += 1
        return "from converse"

    monkeypatch.setattr(agent, "_strands_agent", fake_strands)
    monkeypatch.setattr(agent, "_converse_loop", fake_converse)
    return calls, state


class TestRuntimeChoice:
    def test_strands_is_preferred(self, runtimes):
        calls, _ = runtimes
        reply, runtime = agent.run(ctx(), [])
        assert (reply, runtime) == ("from strands", "strands-agents")
        assert calls["converse"] == 0

    def test_missing_library_falls_back(self, runtimes):
        calls, state = runtimes
        state["strands_raises"] = ImportError("No module named 'strands'")
        reply, runtime = agent.run(ctx(), [])
        assert (reply, runtime) == ("from converse", "bedrock-converse")
        assert calls["converse"] == 1

    def test_a_strands_bug_falls_back_when_nothing_has_happened(self, runtimes):
        """A version mismatch should not take the chat down; our own loop can answer."""
        calls, state = runtimes
        state["strands_raises"] = TypeError("unexpected keyword argument 'tool_spec'")
        reply, runtime = agent.run(ctx(), [])
        assert (reply, runtime) == ("from converse", "bedrock-converse")
        assert calls["converse"] == 1


class TestFallbackIsRefusedWhenItWouldBeWrong:
    def test_a_tool_that_already_ran_must_not_run_twice(self, runtimes):
        """create_watch and prepare_application are not safe to repeat."""
        calls, state = runtimes
        state["strands_raises"] = RuntimeError("stream closed mid-turn")
        c = ctx()
        c.actions.append({"type": "watch_created", "watch_id": "w_1"})
        with pytest.raises(RuntimeError):
            agent.run(c, [])
        assert calls["converse"] == 0, "the turn was retried after a tool had already run"

    @pytest.mark.parametrize("failure", [
        ModelUnavailable("blocked"),
        RuntimeError("AccessDeniedException: you don't have access to the model"),
        RuntimeError("Operation not allowed"),
        RuntimeError("ThrottlingException: slow down"),
    ])
    def test_an_unreachable_model_is_not_retried(self, runtimes, failure):
        """A second attempt fails the same way, slower, and bills twice."""
        calls, state = runtimes
        state["strands_raises"] = failure
        with pytest.raises(type(failure)):
            agent.run(ctx(), [])
        assert calls["converse"] == 0


class TestContextIsAlwaysReleased:
    """The holder is process-wide; a leaked context would serve the next user."""

    def test_after_success(self, runtimes):
        agent.run(ctx(), [])
        assert agent.CTX.current is None

    def test_after_a_failure_that_is_re_raised(self, runtimes):
        _, state = runtimes
        state["strands_raises"] = ModelUnavailable("blocked")
        with pytest.raises(ModelUnavailable):
            agent.run(ctx(), [])
        assert agent.CTX.current is None
