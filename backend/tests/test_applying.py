import unittest

import helpers  # noqa: F401

from career_agent.applying import fit_option, is_consent, map_field, norm_label, strip_unsupported_numbers
from career_agent.demo import DEMO_FACTS, DEMO_SAVED_ANSWERS, PORTAL_SEED_JOBS
from career_agent.handlers import portal as portal_handler
from career_agent.sources.portal import parse_form


def apply_html():
    job = dict(PORTAL_SEED_JOBS[0], id="nw-100", requisition_id="REQ-1", published_at="2026-09-17T00:00:00+00:00")
    return portal_handler.apply_page(job)["body"]


class FormReading(unittest.TestCase):
    def test_parse_portal_form(self):
        form = parse_form(apply_html())
        names = {f["name"]: f for f in form["fields"]}
        self.assertIn("resume", names)
        self.assertEqual(names["resume"]["type"], "file")
        self.assertTrue(names["email"]["required"])
        self.assertFalse(names["gender"]["required"])
        self.assertEqual(names["work_authorization"]["label"], "Are you legally authorized to work in India?")
        self.assertEqual(len(form["signature"]), 64)
        self.assertEqual(parse_form(apply_html())["signature"], form["signature"])

    def test_signature_changes_when_required_question_added(self):
        html = apply_html()
        changed = html.replace('<label for="start_date">', '<label for="notice">Notice period *</label><input id="notice" name="notice" required><label for="start_date">')
        self.assertNotEqual(parse_form(html)["signature"], parse_form(changed)["signature"])

    def test_mapping_demo_profile(self):
        form = parse_form(apply_html())
        out, unknown = {}, []
        for f in form["fields"]:
            m = map_field(f, DEMO_FACTS, DEMO_SAVED_ANSWERS, "note")
            if m is None:
                if f["required"] and f["type"] != "checkbox":
                    unknown.append(f["label"])
                continue
            value, source = m
            if f.get("options") and f["type"] == "select":
                value = fit_option(f["options"], value)
            out[f["name"]] = value
        self.assertEqual(out["first_name"], "Aarav")
        self.assertEqual(out["graduation_year"], "2027")
        self.assertEqual(out["work_authorization"], "yes")
        self.assertEqual(out["gender"], "decline")  # never inferred
        self.assertEqual(unknown, ["Earliest start date"])  # asks instead of guessing

    def test_saved_answer_by_label(self):
        f = {"name": "start_date", "label": "Earliest start date", "type": "date", "required": True, "options": []}
        self.assertEqual(map_field(f, DEMO_FACTS, {"Earliest start date": "2027-01-10"}, None)[0], "2027-01-10")

    def test_unverified_work_authorization_is_unknown(self):
        f = {"name": "wa", "label": "Are you legally authorized to work in India?", "type": "select", "required": True,
             "options": [{"value": "yes", "label": "Yes"}]}
        facts = dict(DEMO_FACTS, work_authorization={"value": None, "verified": False})
        self.assertIsNone(map_field(f, facts, {}, None))

    def test_strip_invented_numbers(self):
        text = "I reduced latency from 900 ms to 350 ms. I led a team of 40 engineers."
        self.assertEqual(strip_unsupported_numbers(text, "latency from 900 ms to 350 ms"), "I reduced latency from 900 ms to 350 ms.")

    def test_norm(self):
        self.assertEqual(norm_label("University / College *"), "university college")


if __name__ == "__main__":
    unittest.main()


class UnsupportedNumberBoundaries(unittest.TestCase):
    """A figure only counts as supported when it appears as a figure.

    Substring matching let a fabricated claim through whenever its digits
    happened to sit inside a larger number in the source.
    """

    SOURCE = "Graduated 2027. Reduced latency from 900 ms to 350 ms."

    def test_fabricated_number_inside_a_larger_one_is_dropped(self):
        self.assertEqual(strip_unsupported_numbers("I have 5 years of experience.", self.SOURCE), "")

    def test_real_numbers_are_kept(self):
        for claim in ("Cut latency to 350 ms.", "Graduating in 2027."):
            self.assertEqual(strip_unsupported_numbers(claim, self.SOURCE), claim)

    def test_sentence_without_numbers_is_untouched(self):
        claim = "I build serverless services on AWS."
        self.assertEqual(strip_unsupported_numbers(claim, self.SOURCE), claim)

    def test_percentage_not_in_source_is_dropped(self):
        self.assertEqual(strip_unsupported_numbers("I improved it by 90%.", self.SOURCE), "")


class TestRegexesSurviveTheirOwnSource:
    r"""A compiled pattern must not contain control characters.

    Written after the same mistake three times: a `\b` word boundary that passed
    through a shell heredoc arrives as the escape `\x08`, a literal backspace.
    The module imports, the regex compiles, every test that does not exercise
    that exact branch passes, and the feature is silently dead - a consent field
    went unrecognised and blocked whole application packets. Checking the
    compiled pattern catches it at the point the mistake is made.
    """

    def test_no_compiled_pattern_contains_a_control_character(self):
        import importlib
        import pkgutil
        import re as _re

        import career_agent

        offenders = []
        for mod in pkgutil.walk_packages(career_agent.__path__, "career_agent."):
            try:
                loaded = importlib.import_module(mod.name)
            except Exception:  # a module that needs runtime config is not our concern here
                continue
            for name, value in vars(loaded).items():
                if isinstance(value, _re.Pattern) and any(ord(c) < 32 for c in str(value.pattern)):
                    offenders.append(f"{mod.name}.{name}")
        assert offenders == [], f"control characters in compiled patterns: {offenders}"


class TestConsentIsRecognisedWhateverWidgetRendersIt:
    """Greenhouse renders a privacy acknowledgement as a one-option select, not a
    checkbox. Matching only checkboxes left it as an unanswerable required field,
    which blocked every packet for that employer."""

    def test_a_single_answer_select_acknowledgement_is_a_consent(self):
        field = {"label": "I acknowledge that I have read the Candidate Privacy Notice",
                 "type": "select", "required": True, "options": [{"label": "Yes", "value": "1"}]}
        assert is_consent(field) is True

    def test_a_checkbox_is_still_a_consent(self):
        assert is_consent({"label": "I agree to the terms", "type": "checkbox", "required": True,
                           "options": []}) is True

    def test_an_ordinary_question_is_not_a_consent(self):
        assert is_consent({"label": "What is your current job title?", "type": "text", "required": True,
                           "options": []}) is False

    def test_a_real_multiple_choice_question_is_not_a_consent(self):
        """"Do you agree with our engineering values" with five answers is a question."""
        field = {"label": "How strongly do you agree with this statement?", "type": "select", "required": True,
                 "options": [{"label": str(n), "value": str(n)} for n in range(5)]}
        assert is_consent(field) is False


class TestTheResumeAnswersWhatEmployersKeepAsking:
    FACTS = {"name": "Asha Rao",
             "experience": [{"title": "Backend Engineer", "company": "Northwind", "end": "Present"},
                            {"title": "Intern", "company": "Older Place", "end": "2024"}]}

    def field(self, label, ftype="text"):
        return {"label": label, "name": label.lower().replace(" ", "_"), "type": ftype,
                "required": True, "options": []}

    def test_legal_name_is_the_name(self):
        assert map_field(self.field("What is your Legal Name?"), self.FACTS, {}, None) == ("Asha Rao", "resume:name")

    def test_current_employer_comes_from_the_ongoing_role(self):
        got = map_field(self.field("What is the name of your current employer?"), self.FACTS, {}, None)
        assert got == ("Northwind", "resume:experience")

    def test_current_title_comes_from_the_ongoing_role(self):
        got = map_field(self.field("What is your current job title?"), self.FACTS, {}, None)
        assert got == ("Backend Engineer", "resume:experience")

    def test_an_empty_resume_does_not_invent_an_employer(self):
        assert map_field(self.field("What is your current employer?"), {"name": "Asha"}, {}, None) is None
