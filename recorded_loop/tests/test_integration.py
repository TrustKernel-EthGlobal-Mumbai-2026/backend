import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from recorded_loop.source_adapter import build_case,retrieve_for_review
from recorded_loop.verifier import assess_original,assess_review
from recorded_loop.runner import run_case


class RecordedIntegrationTests(unittest.TestCase):
    def test_actual_original_protocol_contrast_and_preserved_failure(self):
        sol=build_case('sol-0530a9827c2c')
        terra=build_case('terra-2f66dbe7f15d')
        self.assertEqual(sol['call_context']['output_event']['seq'],69)
        self.assertEqual(terra['call_context']['output_event']['seq'],75)
        before=assess_original(sol)
        self.assertEqual(before['protocol_status'],'FAIL')
        self.assertEqual(assess_original(terra)['protocol_status'],'PASS')
        receipt=retrieve_for_review(sol,'E_SNAPSHOT')
        review=assess_review(sol,receipt)
        self.assertEqual(review['status'],'PASS')
        self.assertTrue(review['review_ready'])
        self.assertEqual(review['historical_protocol_status'],'FAIL')
        self.assertIsNone(review['clearance'])
        self.assertIsNone(review['historical_clearance'])
        self.assertEqual(assess_original(sol),before)

    def test_posthoc_read_never_becomes_historical_delivery_or_fresh_market_data(self):
        packet=build_case('sol-0530a9827c2c')
        original=copy.deepcopy(packet)
        self.assertEqual(packet['evidence']['E_SNAPSHOT']['access']['input_exposures'],[])
        receipt=retrieve_for_review(packet,'E_SNAPSHOT')
        self.assertEqual(receipt['layer'],'new_reviewer_retrieval')
        self.assertFalse(receipt['historical_tool_invocation_created'])
        self.assertIsNone(receipt['source_version'])
        self.assertEqual(packet,original)

    def test_reviewer_receipt_from_other_recording_is_rejected(self):
        sol=build_case('sol-0530a9827c2c');terra=build_case('terra-2f66dbe7f15d')
        receipt=retrieve_for_review(terra,'E_SNAPSHOT')
        result=assess_review(sol,receipt)
        self.assertFalse(result['review_ready'])
        self.assertNotEqual(result['status'],'PASS')

    def test_actual_replay_persistence_and_response_order(self):
        with tempfile.TemporaryDirectory() as temporary,contextlib.redirect_stdout(io.StringIO()):
            path=Path(temporary)/'sol'
            result=run_case('sol-0530a9827c2c',path,'integration:recorded:sol')
            self.assertEqual(result['original_protocol_status'],'FAIL')
            self.assertEqual(result['posthoc_review_status'],'PASS')
            self.assertEqual(result['historical_agent_remediation'],'UNOBSERVED')
            events=[json.loads(line) for line in (path/'trace.jsonl').read_bytes().splitlines()]
            kinds=[e['kind'] for e in events]
            wanted=['historical.assessment.completed','review.feedback.delivered','review.feedback.acknowledged',
                    'review.artifact.requested','review.artifact.retrieved','review.assessment.completed','historical.finding.preserved']
            indices=[kinds.index(k) for k in wanted]
            self.assertEqual(indices,sorted(indices))
            self.assertFalse(any(e['kind']=='llm.start' for e in events))


if __name__=='__main__':unittest.main()
