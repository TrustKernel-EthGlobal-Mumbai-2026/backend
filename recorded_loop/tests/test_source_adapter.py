"""Selected actual-source fidelity, not an independent semantic benchmark."""
import copy
import unittest

from recorded_loop.source_adapter import (
    SUPPORTED_RUNS, SourceIntegrityError, audit_sources, build_case, canonical_json,
    retrieve_for_review, validate_case_sources,
)


class RecordedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sol = build_case(SUPPORTED_RUNS[0])
        cls.terra = build_case(SUPPORTED_RUNS[1])

    def rejects(self, packet, mutate):
        changed = copy.deepcopy(packet)
        mutate(changed)
        with self.assertRaises(SourceIntegrityError):
            validate_case_sources(changed)

    def test_actual_selected_call_role_and_spans(self):
        self.assertEqual(self.sol["call_context"]["input_event"]["seq"], 67)
        self.assertEqual(self.sol["call_context"]["output_event"]["seq"], 69)
        self.assertEqual(self.terra["call_context"]["input_event"]["seq"], 73)
        self.assertEqual(self.terra["call_context"]["output_event"]["seq"], 75)
        self.assertEqual((self.terra["claim"]["anchor"]["start"], self.terra["claim"]["anchor"]["end"]), (346, 351))
        self.assertEqual(self.sol["claim"]["kind"], "relational_close")
        self.assertIsNone(self.sol["claim"]["mapping"]["value"])

    def test_actual_protocol_difference_preserved(self):
        sol = [r for r in self.sol["prefix"]["tool_invocations"] if r["tool"] == "get_verified_market_snapshot"]
        terra = [r for r in self.terra["prefix"]["tool_invocations"] if r["tool"] == "get_verified_market_snapshot"]
        self.assertEqual(sol, [])
        self.assertEqual(len(terra), 1)
        self.assertEqual(self.terra["evidence"]["E_SNAPSHOT"]["access"]["retrieval_event_seqs"], [63])

    def test_decoded_exposures_retain_original_human_role_and_container_binding(self):
        for packet in (self.sol, self.terra):
            exposure = packet["evidence"]["E_PRICE"]["access"]["input_exposures"][0]
            self.assertEqual(exposure["mode"], "decoded_envelope_presence")
            self.assertEqual(exposure["message_role"], "human")
            self.assertEqual(exposure["anchor"]["transform"]["name"], "tool_return_prefix_then_json_parse")
            self.assertEqual(exposure["anchor"]["transform"]["json_pointer"], "/evidence/content")
            self.assertEqual(validate_case_sources(packet)["status"], "PASS")
        self.assertEqual(self.sol["evidence"]["E_SNAPSHOT"]["access"]["input_exposures"], [])

    def test_no_observed_source_version_or_freshness_fabricated(self):
        for packet in (self.sol, self.terra):
            self.assertFalse(packet["source"]["trustkernel_feedback"])
            self.assertEqual(packet["coverage"]["original_agent_response_to_new_review"], "UNOBSERVED")
            self.assertNotIn("max_age_seconds", packet)
            for evidence in packet["evidence"].values():
                self.assertIsNone(evidence["source_version"])
                self.assertEqual(evidence["date_precision"], "date")

    def test_all_six_raw_sources_audited_by_parent_helper(self):
        audit = audit_sources()
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(len(audit["runs"]), 6)
        self.assertEqual(audit["total_events"], 1253)
        self.assertFalse(audit["original_feedback_enabled"])

    def test_hash_and_manifest_omission_rejected(self):
        self.rejects(self.sol, lambda p: p["source_files"][0].update(sha256="0" * 64))
        self.rejects(self.sol, lambda p: p["source_files"].pop())

    def test_call_time_role_and_identity_mutations_rejected(self):
        self.rejects(self.sol, lambda p: p["call_context"]["input_event"].update(timestamp="2099-01-01T00:00:00Z"))
        self.rejects(self.sol, lambda p: p["call_context"].update(actor="News Analyst"))
        self.rejects(self.sol, lambda p: p["call_context"]["output_event"].update(span_id="wrong-call"))

    def test_raw_prefix_omission_and_normalized_invocation_suppression_rejected(self):
        self.rejects(self.sol, lambda p: p["prefix"]["events"].pop(0))
        self.rejects(self.terra, lambda p: p["prefix"].update(tool_invocations=[]))
        self.rejects(self.terra, lambda p: p["prefix"].update(retrievals=[]))

    def test_span_and_original_instruction_mutations_rejected(self):
        self.rejects(self.terra, lambda p: p["claim"]["anchor"].update(end=350))
        self.rejects(self.sol, lambda p: p["instruction"].update(required_tool="get_stock_data"))

    def test_transform_and_role_spoofing_rejected(self):
        def transform(packet):
            packet["evidence"]["E_PRICE"]["access"]["input_exposures"][0]["anchor"]["transform"]["container_sha256"] = "0" * 64
        self.rejects(self.sol, transform)
        self.rejects(self.sol, lambda p: p["evidence"]["E_PRICE"]["access"]["input_exposures"][0].update(message_role="tool"))
        self.rejects(self.sol, lambda p: p["call_context"]["messages"][1].update(role="tool"))

    def test_source_version_precision_and_historical_response_fabrication_rejected(self):
        self.rejects(self.sol, lambda p: p["evidence"]["E_SNAPSHOT"].update(source_version="new-version"))
        self.rejects(self.sol, lambda p: p["evidence"]["E_PRICE"].update(date_precision="second"))
        self.rejects(self.sol, lambda p: p["coverage"].update(original_agent_response_to_new_review="CORRECTED"))

    def test_receipts_are_new_reviewer_events_without_mutating_original(self):
        before = canonical_json(self.sol)
        first = retrieve_for_review(self.sol, "E_SNAPSHOT", reviewed_at="2026-11-02T18:00:00Z")
        second = retrieve_for_review(self.sol, "E_SNAPSHOT", reviewed_at="2026-11-02T18:00:00Z")
        self.assertNotEqual(first["receipt_id"], second["receipt_id"])
        self.assertEqual(first["layer"], "new_reviewer_retrieval")
        self.assertFalse(first["original_history_modified"])
        self.assertFalse(first["historical_tool_invocation_created"])
        self.assertEqual(first["source_anchor"], self.sol["evidence"]["E_SNAPSHOT"]["anchor"])
        self.assertEqual(before, canonical_json(self.sol))
        self.assertEqual(self.sol["evidence"]["E_SNAPSHOT"]["access"]["retrieval_event_seqs"], [])

    def test_receipt_backdating_naive_time_unknown_key_and_bad_source_rejected(self):
        for when in ("2026-10-28T00:00:00Z", "2026-11-02T18:00:00", "garbage", "2026-11-02T18:00:00-00:00"):
            with self.assertRaises(SourceIntegrityError):
                retrieve_for_review(self.sol, "E_SNAPSHOT", reviewed_at=when)
        with self.assertRaises(SourceIntegrityError):
            retrieve_for_review(self.sol, "E_UNKNOWN")

    def test_builds_are_deterministic_and_detached(self):
        again = build_case(SUPPORTED_RUNS[0])
        self.assertEqual(canonical_json(self.sol), canonical_json(again))
        again["report"]["text"] = "edited"
        self.assertNotEqual(self.sol["report"]["text"], "edited")
        with self.assertRaises(SourceIntegrityError):
            build_case("not-an-approved-source")


if __name__ == "__main__":
    unittest.main()
