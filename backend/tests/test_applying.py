import unittest

import helpers  # noqa: F401

from career_agent.applying import fit_option, map_field, norm_label, strip_unsupported_numbers
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
