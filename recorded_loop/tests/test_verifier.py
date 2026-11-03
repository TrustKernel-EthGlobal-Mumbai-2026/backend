"""Only recorded-loop verifier tests; no old builders/discovery/imports."""
from decimal import Decimal
import copy
import unittest

from recorded_loop import verifier as v
from recorded_loop import source_adapter as sa


SOL='sol-0530a9827c2c'
TERRA='terra-2f66dbe7f15d'


def rebind(packet):
    body=copy.deepcopy(packet);body.pop('packet_id',None)
    packet['packet_id']='recorded-case:'+sa.digest(body)
    return packet


def redigest(receipt):
    body=copy.deepcopy(receipt);body.pop('receipt_digest',None)
    receipt['receipt_digest']=sa.digest(body)
    return receipt


class PrimitiveTests(unittest.TestCase):
    def test_price_selection_requires_explicit_dated_usd_row(self):
        content='Synthetic OHLCV CSV, USD\nDate,Open,High,Low,Close,Volume\n2026-10-28,2550,2600,2510,2540,15000'
        self.assertEqual(v._price_row(content,'2026-10-28')['Close'],'2540')
        with self.assertRaises(v.UnresolvedPrerequisite):v._price_row(content,None)
        with self.assertRaises(v.UnresolvedPrerequisite):v._price_row(content,'2026-10-29')
        with self.assertRaises(v.UnresolvedPrerequisite):v._price_row(content.replace('USD','EUR'),'2026-10-28')

    def test_scalar_parser_rejects_missingness_and_nonfinite_values(self):
        self.assertEqual(v._decimal('2,540'),Decimal('2540'))
        with self.assertRaises(v.UnresolvedPrerequisite):v._decimal(None)
        for value in ['NaN','Infinity','NO_DATA','2,54',True]:
            with self.subTest(value=value),self.assertRaises(v.InvalidSourceBinding):v._decimal(value)


class RecordedCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases={run:sa.build_case(run) for run in (SOL,TERRA)}
        cls.receipts={run:sa.retrieve_for_review(packet,'E_SNAPSHOT',reviewed_at='2026-11-02T18:00:00Z') for run,packet in cls.cases.items()}

    def case(self,run=TERRA):return copy.deepcopy(self.cases[run])
    def receipt(self,run=TERRA):return copy.deepcopy(self.receipts[run])

    def finding(self,assessment,obligation):
        return next(f for f in assessment['findings'] if f['obligation']==obligation)

    def rejected_review(self,packet,receipt,status='ERROR'):
        result=v.assess_review(packet,receipt)
        self.assertEqual(result['status'],status)
        self.assertFalse(result['review_ready'])
        self.assertIsNone(result['readiness_binding'])
        self.assertIsNone(result['historical_clearance'])
        self.assertIsNone(result['clearance'])
        return result

    def test_actual_recorded_protocol_contrast_and_no_global_clearance(self):
        sol=v.assess(self.case(SOL));terra=v.assess(self.case())
        self.assertEqual(sol['status'],'FAIL');self.assertEqual(sol['protocol_status'],'FAIL')
        self.assertEqual(terra['status'],'INCONCLUSIVE');self.assertEqual(terra['protocol_status'],'PASS')
        self.assertEqual(self.finding(sol,'required_snapshot_invocation')['observed']['invocation_seqs'],[])
        self.assertEqual(self.finding(terra,'required_snapshot_invocation')['observed']['invocation_seqs'],[62])
        self.assertEqual(self.finding(terra,'required_snapshot_invocation')['observed']['retrieval_seqs'],[63])
        self.assertIsNone(sol['clearance']);self.assertIsNone(terra['clearance'])

    def test_selected_numeric_cases_pass_only_their_declared_scope(self):
        for run in (SOL,TERRA):
            result=v.assess(self.case(run));f=self.finding(result,'selected_fixture_consistency')
            self.assertEqual(f['status'],'PASS')
            self.assertTrue(f['source_witnesses'])
        sol=self.finding(v.assess(self.case(SOL)),'selected_fixture_consistency')
        self.assertFalse(sol['observed']['source_sentence_fully_verified'])
        self.assertEqual(len(sol['observed']['checked_subclaims']),2)
        self.assertIn('higher high',sol['observed']['unassessed_subclaims'][0])
        terra=self.finding(v.assess(self.case()),'selected_fixture_consistency')
        self.assertEqual(terra['observed']['raw_claim'],'2540')
        self.assertEqual(terra['observed']['valid_date'],'2026-10-28')

    def test_exposure_uses_own_call_and_keeps_human_wrapup_role(self):
        for run in (SOL,TERRA):
            a=v.assess(self.case(run));f=self.finding(a,'original_call_exposure:E_PRICE')
            self.assertEqual(f['status'],'PASS')
            self.assertFalse(f['observed']['attention_or_reliance_established'])
            for exposure in f['observed']['exposures']:
                self.assertEqual(exposure['anchor']['event_seq'],67 if run==SOL else 73)
                self.assertEqual(exposure['message_role'],'human')
                self.assertEqual(exposure['mode'],'decoded_envelope_presence')
                self.assertIsNotNone(exposure['anchor']['transform'])
        self.assertEqual(self.finding(v.assess(self.case(SOL)),'original_call_exposure:E_SNAPSHOT')['status'],'INCONCLUSIVE')

    def test_daily_alignment_does_not_create_intraday_ttl_or_source_versions(self):
        for run in (SOL,TERRA):
            a=v.assess(self.case(run))
            self.assertEqual(self.finding(a,'historical_date_alignment')['status'],'PASS')
            f=self.finding(a,'intraday_freshness')
            self.assertEqual(f['status'],'INCONCLUSIVE')
            self.assertIsNone(f['observed']['ttl_applied'])
            self.assertFalse(f['observed']['source_version_progression_invented'])
            self.assertEqual(self.finding(a,'source_version_semantics')['status'],'INCONCLUSIVE')

    def test_original_feedback_dependency_and_hold_limits_remain_explicit(self):
        for run in (SOL,TERRA):
            a=v.assess(self.case(run))
            for name in ['whole_decision_dependencies','hold_suitability','original_agent_response']:
                self.assertEqual(self.finding(a,name)['status'],'INCONCLUSIVE')
            response=self.finding(a,'original_agent_response')['observed']
            self.assertIs(response['trustkernel_feedback'],False)
            self.assertEqual(response['recorded_response_to_new_review'],'UNOBSERVED')
            self.assertFalse(response['new_model_response_created'])

    def test_new_receipt_review_passes_named_scope_without_rewriting_history(self):
        for run in (SOL,TERRA):
            p=self.case(run);before=v.assess(p);review=v.assess_review(p,self.receipt(run));after=v.assess(p)
            self.assertEqual(before,after)
            self.assertEqual(review['status'],'PASS');self.assertTrue(review['review_ready'])
            self.assertEqual(review['historical_assessment_id'],before['assessment_id'])
            self.assertEqual(review['historical_protocol_status'],'FAIL' if run==SOL else 'PASS')
            self.assertEqual(review['scope'],v.REVIEW_SCOPE)
            self.assertIsNone(review['clearance']);self.assertIsNone(review['historical_clearance'])
            binding=review['readiness_binding']
            self.assertFalse(binding['historical_procedure_cleared']);self.assertFalse(binding['trading_authority'])
            self.assertEqual(binding['source_packet_digest'],sa.digest(p))
            self.assertEqual(binding['receipt_digest'],self.receipt(run)['receipt_digest'])

    def test_receipt_for_other_case_or_evidence_is_rejected(self):
        self.rejected_review(self.case(SOL),self.receipt(TERRA))
        r=sa.retrieve_for_review(self.case(),'E_PRICE',reviewed_at='2026-11-02T18:00:00Z')
        self.rejected_review(self.case(),r)

    def test_tampered_receipt_digest_and_rehashed_source_hash_are_rejected(self):
        r=self.receipt();r['content_digest']='0'*64
        self.rejected_review(self.case(),r)
        r=self.receipt();r['source_anchor']['sha256']='0'*64;redigest(r)
        self.rejected_review(self.case(),r)
        r=self.receipt();r['content']='close=9999';redigest(r)
        self.rejected_review(self.case(),r)

    def test_receipt_cannot_be_backdated_or_impersonate_original_actor(self):
        mutations=[lambda r:r.update(actor='Market Analyst'),
            lambda r:r.update(layer='original_recorded_execution'),
            lambda r:r.update(original_history_modified=True),
            lambda r:r.update(historical_tool_invocation_created=True),
            lambda r:r.update(source_version='fresh-v2'),
            lambda r:r.update(retrieved_at=self.case()['call_context']['output_event']['timestamp']),
            lambda r:r.update(retrieved_at='2026-10-29'),
            lambda r:r.update(receipt_id='original-event:123')]
        for i,mutate in enumerate(mutations):
            with self.subTest(index=i):
                r=self.receipt();mutate(r);redigest(r)
                self.rejected_review(self.case(),r)

    def test_wrong_date_unit_or_scalar_mapping_cannot_pass(self):
        for key,value in [('valid_date','2026-10-29'),('unit','EUR'),('entity','BTC-USD'),('value','9999')]:
            with self.subTest(key=key):
                p=self.case();p['claim']['mapping'][key]=value;rebind(p)
                a=v.assess(p)
                failures=[f for f in a['findings'] if f['status'] in ('ERROR','FAIL')]
                self.assertTrue(failures)
                self.assertIsNone(a['clearance'])

    def test_same_value_from_other_occurrence_does_not_inherit_accepted_mapping(self):
        p=self.case();a=p['claim']['anchor'];a.update(start=433,end=438,quote='2,540');rebind(p)
        result=v.assess(p)
        self.assertIn(result['status'],('ERROR','FAIL'))
        self.assertIsNone(result['clearance'])

    def test_changed_claim_span_source_hash_and_raw_roles_are_rejected(self):
        mutations=[lambda p:p['claim']['anchor'].update(start=347),
            lambda p:p['claim'].update(quote='9999'),
            lambda p:p['source_files'][0].update(sha256='0'*64),
            lambda p:p['call_context']['messages'][3].update(role='tool'),
            lambda p:p['evidence']['E_PRICE']['access']['input_exposures'][0].update(message_role='tool')]
        for i,mutate in enumerate(mutations):
            with self.subTest(index=i):
                p=self.case();mutate(p);rebind(p)
                self.assertEqual(v.assess(p)['status'],'ERROR')

    def test_original_packet_identity_and_prefix_cannot_be_rebound_to_reviewer_data(self):
        p=self.case(SOL);p['claim']['mapping']['value']='9999'
        self.assertEqual(v.assess(p)['status'],'ERROR')
        p=self.case(SOL);p['prefix']['tool_invocations'].append({'tool':'get_verified_market_snapshot','seq':999});rebind(p)
        self.assertEqual(v.assess(p)['status'],'ERROR')
        p=self.case(SOL);p['prefix']['events'].pop();rebind(p)
        self.assertEqual(v.assess(p)['status'],'ERROR')

    def test_malformed_inputs_remain_typed_error_without_readiness(self):
        for packet in [None,{},[],{'packet_id':float('nan')}, {'call_context':[]}]:
            with self.subTest(packet=packet):
                self.assertEqual(v.assess(packet)['status'],'ERROR')
                self.rejected_review(packet,None)
        for receipt in [None,{},[],{'receipt_digest':float('nan')}]:
            with self.subTest(receipt=receipt):self.rejected_review(self.case(),receipt)

    def test_null_list_and_primitive_nested_contexts_are_typed_error(self):
        for context in [None,[],1,'invalid',{'input_event':None,'output_event':[]},
                        {'input_event':1,'output_event':'invalid'}]:
            with self.subTest(context=context):
                result=self.rejected_review({'call_context':context},None)
                self.assertEqual(result['findings'][0]['obligation'],'review_source_binding')
        for key in ['input_event','output_event']:
            for value in [None,[],1,'invalid']:
                with self.subTest(key=key,value=value):
                    p=self.case();p['call_context'][key]=value;rebind(p)
                    self.rejected_review(p,self.receipt())

    def test_outputs_detached_and_content_identities_reproducible(self):
        p=self.case();r=self.receipt();original_p=copy.deepcopy(p);original_r=copy.deepcopy(r)
        a=v.assess(p);b=v.assess_review(p,r)
        self.assertEqual(a,v.assess(p));self.assertEqual(b,v.assess_review(p,r))
        self.assertEqual(p,original_p);self.assertEqual(r,original_r)
        a['findings'][0]['status']='FAIL'
        self.assertNotEqual(a,v.assess(p))
        for result,prefix in [(v.assess(p),'recorded-assessment:'),(v.assess_review(p,r),'recorded-review:')]:
            body=copy.deepcopy(result);saved=body.pop('assessment_id')
            self.assertEqual(saved,prefix+sa.digest(body))
            for finding in result['findings']:
                body=copy.deepcopy(finding);saved=body.pop('finding_id')
                self.assertEqual(saved,'recorded-finding:'+sa.digest(body))

    def test_receipt_and_packet_changes_bind_a_distinct_readiness_result(self):
        p=self.case();r=self.receipt();first=v.assess_review(p,r)
        r['retrieved_at']='2026-11-02T18:01:00Z';redigest(r)
        second=v.assess_review(p,r)
        self.assertTrue(second['review_ready'])
        self.assertNotEqual(first['readiness_binding'],second['readiness_binding'])
        self.assertNotEqual(first['assessment_id'],second['assessment_id'])
        p=self.case();p['claim']['mapping']['unit']='EUR';rebind(p)
        self.rejected_review(p,self.receipt())


if __name__=='__main__':
    unittest.main()
