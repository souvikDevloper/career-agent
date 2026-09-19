
from __future__ import annotations

import base64
import io
import json
import subprocess
from pathlib import Path

import pytest
from helpers import T0  # noqa: F401  (adds src/ to sys.path)
from pypdf import PdfReader

from career_agent import latex_preview
from career_agent.handlers import api

FIXTURE = (Path(__file__).parent / "fixtures" / "jake_resume.tex").read_text(encoding="utf8")
USER = "11111111-2222-3333-4444-555555555555"


def pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)


class TestJakePreview:
    def test_the_profile_generated_source_renders_as_a_resume(self):
        text = pdf_text(latex_preview.render_resume_pdf(FIXTURE))
        for expected in ("AARAV MEHTA", "EDUCATION", "Software Engineering Intern", "May 2026 \u2013 July 2026",
                         "Built a Python FastAPI service on AWS Lambda with DynamoDB", "Languages: Python"):
            assert expected in text

    def test_no_latex_markup_leaks_into_the_preview(self):
        text = pdf_text(latex_preview.render_resume_pdf(FIXTURE))
        for junk in ("\\", "$", "[5pt]", "resumeItem", "{", "}", "\\bullet"):
            assert junk not in text

    def test_escaped_characters_come_out_as_the_characters(self):
        tex = FIXTURE.replace("Built a Python FastAPI service", "Cut cost 40\\% with R\\&D on C\\# \\_x")
        assert "Cut cost 40% with R&D on C# _x" in pdf_text(latex_preview.render_resume_pdf(tex))

    def test_a_long_resume_flows_onto_a_second_page(self):
        items = "\n".join(f"        \\resumeItem{{Delivered improvement number {i} across the platform for customers}}" for i in range(70))
        tex = FIXTURE.replace("\\end{document}", items + "\n\\end{document}")
        assert len(PdfReader(io.BytesIO(latex_preview.render_resume_pdf(tex))).pages) >= 2

    def test_a_long_bullet_wraps_inside_the_margins(self):
        tex = FIXTURE.replace("Reduced p95 latency", "word " * 80 + "Reduced p95 latency")
        assert "Reduced p95 latency" in pdf_text(latex_preview.render_resume_pdf(tex))

    def test_paper_size_follows_the_document_class(self):
        a4 = PdfReader(io.BytesIO(latex_preview.render_resume_pdf(FIXTURE))).pages[0].mediabox
        letter = PdfReader(io.BytesIO(latex_preview.render_resume_pdf(FIXTURE.replace("a4paper", "letterpaper")))).pages[0].mediabox
        assert round(float(a4.width)) == 595 and round(float(letter.width)) == 612

    def test_sources_in_other_templates_are_left_to_the_generic_renderer(self):
        assert latex_preview.render_resume_pdf("\\documentclass{article}\\begin{document}\\section*{Hi}x\\end{document}") is None

    def test_a_patch_that_only_uses_some_macros_still_renders(self):
        tex = "\\documentclass{article}\\begin{document}\\section{Experience}\\resumeSubHeadingListStart\\resumeItem{Solo bullet}\\end{document}"
        assert "Solo bullet" in pdf_text(latex_preview.render_resume_pdf(tex))


def compile_event(latex):
    return {
        "rawPath": "/api/resume/builder/compile",
        "requestContext": {"http": {"method": "POST"}, "requestId": "req-1",
                           "authorizer": {"jwt": {"claims": {"sub": USER, "email": "a@example.test"}}}},
        "headers": {}, "body": json.dumps({"latex": latex}),
    }


class TestCompileEndpoint:
    @pytest.fixture(autouse=True)
    def no_tex_engine(self, monkeypatch):
        def missing(*a, **k):
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", missing)

    def test_without_tex_a_jake_resume_gets_the_laid_out_preview(self):
        res = api.handler(compile_event(FIXTURE), None)
        body = json.loads(res["body"])
        assert res["statusCode"] == 200 and body["engine"] == "resume-preview"
        assert "EDUCATION" in pdf_text(base64.b64decode(body["pdf_b64"]))

    def test_without_tex_other_sources_still_use_the_generic_renderer(self):
        body = json.loads(api.handler(compile_event("\\documentclass{article}\\begin{document}\\section*{A}hello world\\end{document}"), None)["body"])
        assert body["engine"] == "vector-renderer"


class TestChatSeesTheProfile:
    def make_svc(self, facts):
        class Profiles:
            def current(self, uid):
                return {"facts": facts} if facts else None

        class Wf:
            def reserve_usage(self, *a, **k):
                return True

        class Svc:
            wf = Wf()
            profiles = Profiles()

        return Svc()

    def chat(self, monkeypatch, svc, latex):
        seen = {}

        def fake(system, prompt, **k):
            seen["system"], seen["prompt"] = system, prompt
            return {"reply": "ok", "latex_patch": None}

        monkeypatch.setattr(api, "_svc", lambda: svc)
        monkeypatch.setattr(api.llm, "json_call", fake)
        ev = compile_event("x")
        ev["rawPath"] = "/api/resume/builder/chat"
        ev["body"] = json.dumps({"message": "tailor it", "latex_context": latex})
        assert api.handler(ev, None)["statusCode"] == 200
        return seen

    def test_verified_facts_reach_the_model_and_internal_fields_do_not(self, monkeypatch):
        seen = self.chat(monkeypatch, self.make_svc({"name": "Aarav Mehta", "skills": [{"name": "Python"}],
                                                     "work_authorization": {"value": "secret"}, "suggestions": [1]}), "x")
        assert "Aarav Mehta" in seen["prompt"] and "Python" in seen["prompt"]
        assert "secret" not in seen["prompt"] and "suggestions" not in seen["prompt"]

    def test_a_user_without_a_profile_still_gets_an_answer(self, monkeypatch):
        assert "none" in self.chat(monkeypatch, self.make_svc(None), "x")["prompt"]

    def test_a_full_jake_source_is_not_truncated(self, monkeypatch):
        big = FIXTURE + "% padding\n" * 500  # well past the old 6000-character request limit
        assert len(big) > 6000 and big in self.chat(monkeypatch, self.make_svc(None), big)["prompt"]

    def test_the_prompt_tells_the_model_to_keep_jakes_macros(self, monkeypatch):
        system = self.chat(monkeypatch, self.make_svc(None), "x")["system"]
        assert "\\resumeSubheading" in system and "never invent" in system.lower()
