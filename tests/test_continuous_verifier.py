"""Negative controls use temporary authored packets, never private recordings."""
import copy
import unittest

from continuous_verification import verify, validate_result
from test_continuous_contracts import example, rebind


class VerifierTests(unittest.TestCase):
    def assess(self, p):
        result = verify(**p)
        validate_result(result)
        return result

    def outcomes(self, p):
        return [f["outcome"] for f in self.assess(p)["findings"]]

    def test_complete_authored_view(self):
        p = example()
        result = self.assess(p)
        self.assertEqual(result["status"], "ASSESSED")
        self.assertEqual(result["disposition"], "ADVISE")
        self.assertEqual(self.outcomes(p), ["PASS", "PASS"])
        self.assertEqual(result, self.assess(copy.deepcopy(p)))
        self.assertEqual(p["request"]["proposal"]["dependency_completeness"], "UNKNOWN")
        self.assertEqual(result["scope"], "declared_checks_at_checkpoint")

    def test_omission_and_failed_tool(self):
        for mutation in ["omitted", "error"]:
            p = example()
            if mutation == "omitted":
                p["events"][1]["payload"]["included_event_ids"] = []
            else:
                p["events"][0]["payload"]["status"] = "ERROR"
            result = self.assess(p)
            self.assertEqual(self.outcomes(p), ["FAIL", "PASS"])
            self.assertEqual(result["disposition"], "HOLD")
            self.assertEqual(result["findings"][0]["event_ids"][:2], ["event-3", "event-2"])

    def test_unknown_tool_status_is_not_omission(self):
        p = example()
        p["events"][0]["payload"]["status"] = "UNKNOWN"
        self.assertEqual(self.outcomes(p), ["INCONCLUSIVE", "PASS"])
        self.assertEqual(self.assess(p)["disposition"], "RECHECK")

    def test_completion_independent_of_snapshot(self):
        for completion in ["TRUNCATED", "ERROR", "UNKNOWN"]:
            p = example()
            p["events"][2]["payload"]["completion"] = completion
            self.assertEqual(self.outcomes(p), ["INCONCLUSIVE", "INCONCLUSIVE" if completion == "UNKNOWN" else "FAIL"])

    def test_open_phase_cannot_prove_absence(self):
        p = example()
        p["events"][2]["payload"]["phase"] = "OPEN"
        p["events"][1]["payload"]["included_event_ids"] = []
        self.assertEqual(self.outcomes(p), ["INCONCLUSIVE", "INCONCLUSIVE"])

    def test_lagging_missing_and_producer_reported_views(self):
        for mutation in ["ingest", "projection", "missing", "producer"]:
            p = example()
            if mutation == "missing":
                p["events"].pop(0)
            elif mutation == "producer":
                p["checkpoint"]["established_by"]["basis"] = "PRODUCER_REPORTED"
            else:
                key = "ingested_through" if mutation == "ingest" else "projected_through"
                p["checkpoint"]["streams"][0][key] = 2
            result = self.assess(rebind(p))
            self.assertEqual(result["status"], "NOT_READY")
            self.assertEqual(result["disposition"], "HOLD")
            self.assertEqual([f["outcome"] for f in result["findings"]], ["INCONCLUSIVE"] * 2)

    def test_gaps_inside_prefix_only(self):
        p = example()
        for gaps, status in [([[1, 1]], "CAPTURE_GAP"), ([[3, 5]], "CAPTURE_GAP"), ([[4, 5]], "ASSESSED")]:
            p["checkpoint"]["streams"][0]["gaps"] = gaps
            self.assertEqual(self.assess(rebind(p))["status"], status)

    def test_per_stream_vector(self):
        p = example()
        p["checkpoint"]["streams"].append(dict(stream_id="second", requested=1, ingested_through=0, projected_through=0, gaps=[], capabilities=[]))
        self.assertEqual(self.assess(rebind(p))["status"], "NOT_READY")
        self.assertEqual([s["status"] for s in self.assess(p)["readiness"]["streams"]], ["READY", "NOT_READY"])
        # A high watermark in host cannot make another stream ready.
        p["checkpoint"]["streams"][0]["ingested_through"] = 100
        p["checkpoint"]["streams"][0]["projected_through"] = 100
        self.assertEqual(self.assess(rebind(p))["status"], "NOT_READY")

    def test_unknown_or_unreferenced_capabilities(self):
        for name in ["model_input", "tool_lifecycle", "phase_boundaries", "report_completion"]:
            for mutation in ["UNKNOWN", "NOT_CAPTURED", "no_basis", "missing_basis"]:
                p = example()
                c = next(c for c in p["checkpoint"]["streams"][0]["capabilities"] if c["name"] == name)
                if mutation == "no_basis":
                    c["basis_event_ids"] = []
                elif mutation == "missing_basis":
                    c["basis_event_ids"] = ["not-observed"]
                else:
                    c["state"] = mutation
                outcomes = self.outcomes(rebind(p))
                self.assertIn("INCONCLUSIVE", outcomes)
                self.assertNotIn("FAIL", outcomes)

    def test_missing_or_mismatched_input(self):
        for mutation in ["missing", "wrong_revision", "unknown_boundary", "missing_evidence", "missing_causality"]:
            p = example()
            if mutation == "missing":
                p["events"][2]["payload"]["input_event_id"] = None
            elif mutation == "wrong_revision":
                p["events"][1]["payload"]["report_revision"] = 4
            elif mutation == "unknown_boundary":
                p["events"][1]["payload"]["boundary"] = "UNKNOWN"
            elif mutation == "missing_evidence":
                p["events"][1]["payload"]["included_event_ids"] = ["unobserved"]
            else:
                p["events"][2]["parents"] = []
            self.assertEqual(self.outcomes(p)[0], "INCONCLUSIVE")

    def test_late_snapshot_not_in_input(self):
        p = example()
        late = p["events"][0]
        late["sequence"] = 4
        p["events"][1]["sequence"] = 1
        p["events"][2]["sequence"] = 2
        # Add an unrelated observation to keep the prefix contiguous.
        filler = copy.deepcopy(late)
        filler.update(event_id="filler", sequence=3, event_type="observation", payload={})
        p["events"] = p["events"][1:] + [filler, late]
        p["checkpoint"]["streams"][0].update(requested=4, ingested_through=4, projected_through=4)
        p["events"][0]["payload"]["included_event_ids"] = []
        p["events"][0]["parents"] = []
        self.assertEqual(self.outcomes(rebind(p))[0], "FAIL")
        # Even an adapter assertion of inclusion conflicts with same-stream order.
        p["events"][0]["payload"]["included_event_ids"] = ["event-1"]
        self.assertEqual(self.outcomes(p)[0], "INCONCLUSIVE")

    def test_self_future_parent_and_same_stream_cycle(self):
        for parent in ["event-1", "event-2", "event-3"]:
            p = example()
            p["events"][0]["parents"] = [parent]
            result = self.assess(p)
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(result["issues"][0]["code"], "CAUSALITY")
            self.assertIsNone(result["binding"])

    def test_cross_stream_cycle_and_missing_parent(self):
        p = example()
        p["events"][0]["stream_id"] = "tools"
        p["events"][1]["sequence"] = 1
        p["events"][2]["sequence"] = 2
        p["checkpoint"]["streams"][0].update(requested=2, ingested_through=2, projected_through=2)
        p["checkpoint"]["streams"].append(dict(stream_id="tools", requested=1, ingested_through=1, projected_through=1, gaps=[], capabilities=[]))
        p["events"][0]["parents"] = ["event-3"]
        result = self.assess(rebind(p))
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["issues"][0]["code"], "CAUSALITY")
        p["events"][0]["parents"] = ["missing-parent"]
        result = self.assess(p)
        self.assertEqual(result["status"], "NOT_READY")
        self.assertEqual(result["readiness"]["unresolved_parent_ids"], ["missing-parent"])
        self.assertEqual([f["outcome"] for f in result["findings"]], ["INCONCLUSIVE"] * 2)

    def test_report_identity_and_revision_substitution(self):
        for mutation in ["report_id", "revision", "wrong_type"]:
            p = example()
            if mutation == "wrong_type":
                p["request"]["proposal"]["report_event_id"] = "event-1"
            elif mutation == "revision":
                p["events"][2]["payload"]["revision"] += 1
            else:
                p["events"][2]["payload"]["report_id"] = "other-report"
            result = self.assess(p)
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(result["issues"][0]["code"], "REPORT_BINDING")

    def test_cross_stream_causality_does_not_use_ingestion_order(self):
        p = example()
        p["events"][0]["stream_id"] = "tools"
        p["events"][1]["sequence"] = 1
        p["events"][2]["sequence"] = 2
        p["checkpoint"]["streams"][0].update(requested=2, ingested_through=2, projected_through=2)
        p["checkpoint"]["streams"].append(dict(stream_id="tools", requested=1, ingested_through=1, projected_through=1, gaps=[], capabilities=[]))
        p["events"].reverse()
        self.assertEqual(self.outcomes(rebind(p)), ["PASS", "PASS"])
        # Explicit input provenance is still necessary across streams.
        p["events"][1]["parents"] = []
        self.assertEqual(self.outcomes(p)[0], "INCONCLUSIVE")

    def test_structural_errors_and_conflicts(self):
        for mutation in ["duplicate_id", "duplicate_sequence", "outside_prefix", "unregistered_stream", "cross_run", "bad_event", "empty_streams", "wrong_events_type"]:
            p = example()
            if mutation == "duplicate_id":
                p["events"][1]["event_id"] = "event-1"
            elif mutation == "duplicate_sequence":
                p["events"][1]["sequence"] = 1
            elif mutation == "outside_prefix":
                p["events"][0]["sequence"] = 4
            elif mutation == "unregistered_stream":
                p["events"][0]["stream_id"] = "unregistered"
            elif mutation == "cross_run":
                p["events"][0]["run_id"] = "other"
            elif mutation == "empty_streams":
                p["checkpoint"]["streams"] = []
                rebind(p)
            elif mutation == "wrong_events_type":
                p["events"] = None
            else:
                del p["events"][0]["content"]
            with self.subTest(mutation=mutation):
                r = self.assess(p)
                self.assertEqual(r["status"], "ERROR")
                self.assertEqual(r["disposition"], "HOLD")
                self.assertIsNone(r["binding"])
                self.assertTrue(r["issues"])

    def test_stale_checkpoint_policy_binding(self):
        for section, field in [("checkpoint", "revision"), ("policy", "version")]:
            p = example()
            p[section][field] = 1 if section == "checkpoint" else "2"
            self.assertEqual(self.assess(p)["status"], "ERROR")

    def test_policy_explicit_disposition_and_subset(self):
        p = example()
        p["events"][1]["payload"]["included_event_ids"] = []
        p["policy"]["checks"][0]["on_fail"] = "ADVISE"
        self.assertEqual(self.assess(rebind(p))["disposition"], "ADVISE")
        self.assertEqual(self.outcomes(p), ["FAIL", "PASS"])
        p["request"]["checks"] = ["report_completion"]
        self.assertEqual(self.outcomes(p), ["PASS"])

    def test_feedback_observations_do_not_correct_history(self):
        p = example()
        p["events"][1]["payload"]["included_event_ids"] = []
        for i, kind in enumerate(["feedback_delivery", "feedback_inclusion", "feedback_acknowledgement", "correction"], start=4):
            e = copy.deepcopy(p["events"][0])
            e.update(event_id="feedback-"+str(i),sequence=i,event_type=kind,payload=dict(assessment_id="old-assessment",proposal_id="proposal-1",proposal_revision=0,related_event_ids=[]))
            p["events"].append(e)
        p["checkpoint"]["streams"][0].update(requested=7, ingested_through=7, projected_through=7)
        self.assertEqual(self.outcomes(rebind(p)), ["FAIL", "PASS"])


if __name__ == "__main__":
    unittest.main()
