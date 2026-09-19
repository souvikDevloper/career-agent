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


class TestStrandsFollowsTheProvider:
    """Strands is an AWS open-source project and the agent framework here.

    Hardcoding BedrockModel meant a blocked account took Strands out of the loop
    entirely and fell through to our own tool loop - losing the framework for a
    reason that has nothing to do with it.
    """

    def _fake_strands(self, monkeypatch):
        import sys
        import types

        built = {}
        openai_mod = types.ModuleType("strands.models.openai")
        openai_mod.OpenAIModel = lambda **kw: built.setdefault("openai", kw)
        models_mod = types.ModuleType("strands.models")
        models_mod.BedrockModel = lambda **kw: built.setdefault("bedrock", kw)
        for name, mod in (("strands.models", models_mod), ("strands.models.openai", openai_mod)):
            monkeypatch.setitem(sys.modules, name, mod)
        return built

    def test_bedrock_by_default(self, monkeypatch):
        built = self._fake_strands(monkeypatch)
        monkeypatch.delenv("MODEL_PROVIDER", raising=False)
        agent._strands_model()
        assert "bedrock" in built and "openai" not in built

    def test_the_configured_provider_when_bedrock_is_unreachable(self, monkeypatch):
        built = self._fake_strands(monkeypatch)
        monkeypatch.setenv("MODEL_PROVIDER", "openai")
        monkeypatch.setenv("MODEL_API_BASE", "https://models.example.test/v1/")
        monkeypatch.setenv("FALLBACK_MODEL_ID", "some-fast-model")
        monkeypatch.setenv("MODEL_API_KEY", "test-key")
        monkeypatch.setenv("MODEL_API_KEY_PARAM", "")
        from career_agent import llm

        monkeypatch.setattr(llm, "_api_key", None, raising=False)
        agent._strands_model()
        assert "bedrock" not in built, "Strands was dropped instead of pointed at the working model"
        made = built["openai"]
        assert made["model_id"] == "some-fast-model"
        # trailing slash trimmed, or the client builds a double-slashed URL
        assert made["client_args"]["base_url"] == "https://models.example.test/v1"
        assert made["client_args"]["api_key"] == "test-key"


class TestPrepareSaysWhetherWeCanSubmit:
    """Only the test portal accepts a submission from us; every real employer
    ends in ManualHandoff. That is the finished state, not a stall - but the
    agent described a completed packet as pending, and the user read a finished
    application sitting on step 1 of 6 as the system hanging.
    """

    class FakeServices:
        def __init__(self, connector):
            self.connector = connector

        def request_prepare(self, uid, job_key):
            return {"app_id": "app_1", "connector": self.connector}

    def run(self, connector):
        agent.CTX.current = ctx(services=self.FakeServices(connector))
        try:
            return agent.t_prepare_application("greenhouse:stripe:1")
        finally:
            agent.CTX.current = None

    def test_a_live_employer_is_flagged_as_ours_to_hand_over(self):
        got = self.run("amazon-jobs")
        assert got["we_can_submit"] is False
        assert got["ends_in"] == "ManualHandoff"
        assert "does not accept submissions" in got["note"]

    def test_the_one_connector_that_can_submit_says_so(self):
        got = self.run("northwind-test-portal")
        assert got["we_can_submit"] is True
        assert got["ends_in"] == "NeedsApproval"

    def test_an_unknown_connector_is_treated_as_not_submittable(self):
        """Defaulting the other way would promise a submission we cannot make."""
        assert self.run("something-new")["we_can_submit"] is False



class TestAmazonSearchFallback:
    """A narrow recovery path for simple Amazon searches."""

    def parser(self, text):
        from career_agent.handlers import worker
        return worker._fallback_amazon_filters(text)

    def test_extracts_company_role_and_bengaluru_with_punctuation(self):
        assert self.parser("Find Amazon SDE 1 jobs in Bengaluru.") == {
            "company": "Amazon", "role": "sde 1", "location": "bengaluru",
        }

    def test_bangalore_alias_uses_existing_discovery_aliases(self):
        assert self.parser("show me amazon software engineer openings in Bangalore") == {
            "company": "Amazon", "role": "software engineer", "location": "bangalore",
        }

    def test_two_step_search_and_apply_is_not_intercepted(self):
        assert self.parser("find amazon sde 1 jobs and apply to the best one") is None

    def test_two_step_search_and_prepare_is_not_intercepted(self):
        assert self.parser("search amazon roles then prepare an application for the top match") is None

    def test_informational_question_is_not_intercepted(self):
        assert self.parser("what does amazon look for in an sde 1?") is None

    def test_direct_search_runs_only_after_agent_failure_with_no_actions(self, monkeypatch):
        from career_agent.handlers import worker

        class Clock:
            def iso(self):
                return "2026-09-19T10:00:00+00:00"

        class Store:
            def __init__(self):
                self.puts = []
            def put(self, item):
                self.puts.append(item)
            def query(self, *a, **k):
                return []

        class WF:
            def __init__(self):
                self.clock = Clock()
                self.progress = []
            def op_progress(self, uid, op_id, **kw):
                self.progress.append((uid, op_id, kw))

        class Svc:
            def __init__(self):
                self.wf = WF()
                self.store = Store()
            def _reserve_model(self, uid):
                pass
            def is_judge(self, uid):
                return False
            def search(self, uid, op_id, **kw):
                assert kw["filters"] == {"company": "Amazon", "role": "sde 1", "location": "bengaluru"}
                kw["stats"].update({"live_postings": 8})
                return [{"score": 82, "job": {"title": "SDE-1 (FTC)", "location": "Bengaluru"}}]

        monkeypatch.setattr(worker.agent, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model failed")))
        svc = Svc()
        worker.run_chat(svc, "u1", "op1", "Find Amazon SDE 1 jobs in Bengaluru.", "chat", "cid")
        assert svc.wf.progress[-1][2]["status"] == "succeeded"
        assert svc.wf.progress[-1][2]["final"]["runtime"] == "direct-search-fallback"
        assert "SDE-1 (FTC)" in svc.store.puts[-1]["text"]

    def test_successful_agent_is_not_bypassed(self, monkeypatch):
        from career_agent.handlers import worker

        class Clock:
            def iso(self):
                return "2026-09-19T10:00:00+00:00"

        class Store:
            def __init__(self):
                self.puts = []
            def put(self, item):
                self.puts.append(item)
            def query(self, *a, **k):
                return []

        class WF:
            def __init__(self):
                self.clock = Clock()
                self.progress = []
            def op_progress(self, uid, op_id, **kw):
                self.progress.append((uid, op_id, kw))

        class Svc:
            def __init__(self):
                self.wf = WF()
                self.store = Store()
            def _reserve_model(self, uid):
                pass
            def is_judge(self, uid):
                return False
            def search(self, *a, **k):
                raise AssertionError("fallback should not run when the agent searched")

        def fake_run(ctx, history):
            ctx.actions.append({"type": "search", "count": 1})
            return "agent result", "strands-agents"

        monkeypatch.setattr(worker.agent, "run", fake_run)
        svc = Svc()
        worker.run_chat(svc, "u1", "op1", "Find Amazon SDE 1 jobs in Bengaluru.", "chat", "cid")
        assert svc.wf.progress[-1][2]["final"]["runtime"] == "strands-agents"
        assert svc.store.puts[-1]["text"] == "agent result"
