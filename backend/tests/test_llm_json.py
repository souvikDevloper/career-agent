"""Parsing model output.

Bedrock is unreachable on this account, so this layer has never run against a
real response. These pin the two ways good output arrives malformed: a top-level
array, and a reply cut off by the output token limit. Both would otherwise
surface as a 500 the first time the model answers.
"""

from __future__ import annotations

import pytest

from career_agent.llm import extract_json


class TestContainerChoice:
    def test_single_element_array_stays_an_array(self):
        """Preferring '{' unconditionally returned the inner object instead."""
        assert extract_json('[{"title": "SDE Intern"}]') == [{"title": "SDE Intern"}]

    def test_array_wrapped_in_prose(self):
        assert extract_json('Here are the roles:\n[{"a": 1}]\nHope that helps.') == [{"a": 1}]

    def test_array_in_a_fenced_block(self):
        assert extract_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]

    def test_object_containing_an_array_is_still_an_object(self):
        assert extract_json('{"questions": [{"q": "why?"}]}') == {"questions": [{"q": "why?"}]}

    def test_multi_element_array(self):
        assert extract_json('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


class TestTruncatedOutput:
    """maxTokens is the ordinary failure. Recover locally rather than pay again."""

    def test_nothing_complete_is_reported_rather_than_guessed(self):
        """An empty object here would be a fabricated answer, not a recovered one."""
        with pytest.raises(ValueError):
            extract_json('{"summary": "They invited you to an assessm')

    def test_keeps_the_fields_that_completed(self):
        got = extract_json('{"type": "rejection", "confidence": 0.9, "summary": "They passe')
        assert got["type"] == "rejection"
        assert got["confidence"] == 0.9

    def test_cut_between_array_elements(self):
        got = extract_json('{"edits": [{"section": "Skills", "after": "Python"}, {"section": "Pro')
        assert [e["section"] for e in got["edits"]] == ["Skills"]

    def test_cut_after_a_trailing_comma(self):
        got = extract_json('{"a": 1, "b": 2,')
        assert got == {"a": 1, "b": 2}

    def test_truncated_array_at_top_level(self):
        got = extract_json('[{"q": "one"}, {"q": "tw')
        assert got == [{"q": "one"}]

    def test_escaped_quote_does_not_end_the_string(self):
        got = extract_json('{"quote": "she said \\"hi\\" then", "n": 1}')
        assert got["quote"] == 'she said "hi" then'


class TestUnparseable:
    @pytest.mark.parametrize("text", ["", "I cannot help with that.", "{{{{", "}]"])
    def test_raises_rather_than_returning_something_wrong(self, text):
        """Callers catch ValueError and fall back; a bad guess would be worse."""
        with pytest.raises(ValueError):
            extract_json(text)


class TestTruncationIsNeverWrong:
    """Cut a realistic response at every offset; recovery may lose fields, never invent one."""

    DOC = (
        '{"skills": [{"skill": "Python", "evidence": "Built a Flask API", "level": 0.8}, '
        '{"skill": "AWS", "evidence": "Deployed Lambda, said \\"serverless\\"", "level": 0.6}], '
        '"experience": 1.5, "experience_evidence": ["Intern at Acme"], "responsibilities": 0.7, '
        '"explanation": "Strong overlap on backend.", "requirements": {"must": ["Python"], "nice": []}}'
    )

    def _subset(self, got, full, path=""):
        """Every value recovery returned must be exactly what the original had there."""
        if isinstance(full, dict):
            assert isinstance(got, dict), f"{path}: shape changed"
            for k, v in got.items():
                assert k in full, f"{path}.{k}: invented key"
                self._subset(v, full[k], f"{path}.{k}")
        elif isinstance(full, list):
            assert isinstance(got, list), f"{path}: shape changed"
            assert len(got) <= len(full), f"{path}: invented elements"
            for i, v in enumerate(got):
                self._subset(v, full[i], f"{path}[{i}]")
        else:
            assert got == full, f"{path}: value changed"

    def test_every_prefix(self):
        import json

        full = json.loads(self.DOC)
        recovered = 0
        for cut in range(1, len(self.DOC) + 1):
            try:
                got = extract_json(self.DOC[:cut])
            except ValueError:
                continue
            self._subset(got, full)
            recovered += 1
        # Most of the document is recoverable; the point is that none of it is wrong.
        assert recovered > len(self.DOC) // 2, f"only {recovered}/{len(self.DOC)} prefixes recovered"
