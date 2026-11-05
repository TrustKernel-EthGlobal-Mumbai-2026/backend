"""Authored offline plumbing only. Backend callbacks are provisional doubles."""
from dataclasses import replace
import unittest

from continuous_verification.tradingagents import (
    BoundaryError, FeedbackBoundary, Limits, LocalFeedback,
)


class BoundaryTests(unittest.TestCase):
    def make_boundary(self, **kwargs):
        self.events = []
        self.receipts = []

        def assessment_double(binding):
            result = LocalFeedback(binding, f"authored-{len(self.receipts)}", "READY", "ADVISE", "[]")
            self.receipts.append(result)
            return result

        defaults = dict(run_id="authored-run", proposal_id="report", policy_binding="authored-policy",
                        checkpoint=lambda record: f"authored-prefix-{record['revision']}",
                        assess=assessment_double, emit=lambda kind, data: self.events.append((kind, data)))
        return FeedbackBoundary(**(defaults | kwargs))

    def deliver(self, host):
        payload = host.verify()
        call_id = f"call-{host.counts['verify_calls']}"
        host.observe_tool_return(call_id, payload)
        host.observe_next_input("input", [(call_id, payload)])
        return payload

    def test_voluntary_omission_and_no_implicit_enforcement(self):
        host = self.make_boundary()
        host.submit("Authored report")
        self.assertFalse(host.report_boundary_allowed())
        self.assertEqual(host.counts["verify_calls"], 0)
        self.deliver(host)
        self.assertFalse(host.report_boundary_allowed())

    def test_delivery_input_ack_and_at_use_authorizer_are_distinct(self):
        allowed = [True]
        host = self.make_boundary(authorize=lambda binding, result: allowed[0])
        host.submit("Authored report")
        payload = host.verify()
        self.assertFalse(host.report_boundary_allowed())
        host.observe_tool_return("c", payload)
        self.assertFalse(host.report_boundary_allowed())
        host.acknowledge(host.feedback.assessment_id, "Authored acknowledgement")
        self.assertFalse(host.report_boundary_allowed())
        host.observe_next_input("i", [("other", payload), ("c", "different")])
        self.assertFalse(host.report_boundary_allowed())
        host.observe_next_input("i2", [("c", payload)])
        self.assertTrue(host.report_boundary_allowed())
        allowed[0] = False
        self.assertFalse(host.report_boundary_allowed())

    def test_revision_preserves_old_proposal_and_rejects_old_result(self):
        host = self.make_boundary(authorize=lambda *_: True)
        old = host.submit("Authored first")
        self.deliver(host)
        host.submit("Authored revision")
        self.assertFalse(host.report_boundary_allowed())
        host.assess = lambda _: self.receipts[0]
        with self.assertRaisesRegex(BoundaryError, "Stale"):
            host.verify()
        self.assertEqual(host.proposals[0]["text"], "Authored first")
        self.assertNotEqual(host.current, old)

    def test_separate_allowances_and_failed_refresh_invalidates(self):
        host = self.make_boundary(limits=Limits(1, 2, 1), authorize=lambda *_: True)
        host.submit("Authored")
        self.deliver(host)
        def unavailable():
            raise TimeoutError("authored unavailable source")
        with self.assertRaises(TimeoutError):
            host.source_round([unavailable])
        self.assertFalse(host.report_boundary_allowed())
        self.assertEqual(host.counts, dict(source_rounds=1, verify_calls=1, remediations=0))
        with self.assertRaises(BoundaryError):
            host.source_round([])
        host.submit("Abstain from defective price")
        self.deliver(host)
        with self.assertRaises(BoundaryError):
            host.verify()
        with self.assertRaises(BoundaryError):
            host.submit("Excess correction")
        host.abstain("No supported replacement price")
        self.assertFalse(host.report_boundary_allowed())

    def test_unready_gap_error_and_hold_cannot_release(self):
        for readiness, disposition in [("NOT_READY", "ADVISE"), ("CAPTURE_GAP", "ADVISE"),
                                       ("ERROR", "ADVISE"), ("READY", "HOLD"), ("READY", "RECHECK")]:
            with self.subTest(readiness=readiness, disposition=disposition):
                host = self.make_boundary(authorize=lambda *_: True)
                host.submit("Authored")
                host.assess = lambda b: LocalFeedback(b, "authored", readiness, disposition, "[]")
                self.deliver(host)
                self.assertFalse(host.report_boundary_allowed())

    def test_timeout_spends_verify_allowance_and_clears_advice(self):
        host = self.make_boundary(limits=Limits(0, 2, 0), authorize=lambda *_: True)
        host.submit("Authored")
        self.deliver(host)
        def timeout(_):
            raise TimeoutError("authored backend timeout")
        host.assess = timeout
        with self.assertRaises(TimeoutError):
            host.verify()
        self.assertFalse(host.report_boundary_allowed())
        self.assertEqual(host.counts["verify_calls"], 2)

    def test_wrong_run_checkpoint_policy_digest_or_revision_rejected(self):
        for field, value in [("run_id", "other"), ("checkpoint_id", "later"),
                             ("policy_binding", "other"), ("text_digest", "other"), ("revision", 2)]:
            with self.subTest(field=field):
                host = self.make_boundary()
                host.submit("Authored")
                host.assess = lambda b: LocalFeedback(replace(b, **{field: value}), "a", "READY", "ADVISE", "[]")
                with self.assertRaises(BoundaryError):
                    host.verify()


if __name__ == "__main__":
    unittest.main()
