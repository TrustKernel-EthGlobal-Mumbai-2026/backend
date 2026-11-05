"""Readiness controls; optional actual-import runner tests are separate."""
import unittest
from tools.tradingagents_integration import PROFILE, preflight_plan


class ReadinessPlanTests(unittest.TestCase):
    def test_default_plan_disables_paid_and_preserves_unknowns(self):
        plan = preflight_plan()
        self.assertFalse(plan["execution_enabled"])
        self.assertIn("NOT_OPENED", plan["budget_status"])
        self.assertIn("NOT_CHECKED", plan["model_access"])
        self.assertEqual(plan["new_user_approval"], "REQUIRED")
        self.assertEqual(PROFILE["tool_choice"], "auto")
        self.assertFalse(PROFILE["live_sources"])
        self.assertEqual(PROFILE["cumulative_hard_limit_usd"], 5)
        self.assertEqual(PROFILE["max_model_calls"], 4)
        plan["profile"]["model"] = "changed"
        self.assertEqual(PROFILE["model"], "gpt-6.1-sol")
