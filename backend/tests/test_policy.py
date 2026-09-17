import unittest

import helpers  # noqa: F401

from career_agent import policy


class PolicyParity(unittest.TestCase):
    def test_reference_rules(self):
        eng = policy.ReferenceEngine()
        base = dict(user_id="u1", is_judge=False, action=policy.SUBMIT, app_owner="u1", target_environment="test")
        d = eng.authorize(policy.Request(**base, context={"mode": "auto_above_80", "score": 80, "mandate_active": True, "auto_eligible": True}))
        self.assertFalse(d.allowed)
        d = eng.authorize(policy.Request(**base, context={"mode": "auto_above_80", "score": 81, "mandate_active": True, "auto_eligible": True}))
        self.assertTrue(d.allowed)

    def test_cedar_matches_reference_on_grid(self):
        try:
            cedar = policy.CedarEngine()
        except ImportError:
            self.skipTest("cedarpy not installed (runs in CI)")
        ref = policy.ReferenceEngine()
        mismatches = []
        for req in policy.context_grid():
            a, b = cedar.authorize(req), ref.authorize(req)
            if a.allowed != b.allowed or a.errors:
                mismatches.append((req, a, b))
        self.assertEqual(mismatches[:3], [])


if __name__ == "__main__":
    unittest.main()
