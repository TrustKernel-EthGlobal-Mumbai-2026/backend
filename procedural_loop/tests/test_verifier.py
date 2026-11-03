"""Named verifier tests; no historical test discovery or source rebuilds."""
from datetime import timedelta
from decimal import Decimal
import copy
import unittest

from procedural_loop import verifier as v
from procedural_loop import contracts as c


T0='2026-11-02T00:00:00Z'


def evidence(id_='e1',version='1',value='2540',valid=T0,retrieved=T0,supersedes=None):
    content=f'Synthetic ETH-USD quote: {value} USD at {valid}. Authored test data.'
    return {'id':id_,'source_id':'synthetic-quote-feed','source_version':version,
        'supersedes':supersedes or [],'valid_at':valid,'retrieved_at':retrieved,'recorded_at':retrieved,
        'content':content,'content_digest':c.text_digest(content),
        'pointer':{'uri':'fixture://verifier-tests','json_pointer':'/observations/'+id_,'span':[0,len(content)]},
        'run_id':'test-run','actor_id':'quote-source','call_id':'read-'+id_,'causal_refs':['obs-'+id_],
        'status':'AVAILABLE'}


def packet():
    ev=evidence()
    start=ev['content'].index('2540')
    return {'schema_version':c.SCHEMA_VERSION,'packet_id':'packet-1','run_id':'test-run',
        'context':{'id':'context','revision':1,'observed_at':'2026-11-02T00:00:30Z','event_refs':['obs-e1','submit-1']},
        'capabilities':[{'name':name,'scope':'test-run','state':'CAPTURED','detail':'Authored complete fixture scope only.'} for name in sorted(v.REQUIRED_CAPABILITIES)],
        'evidence':[ev],
        'proposal':{'id':'proposal-1','revision':1,'as_of':'2026-11-02T00:00:30Z','created_at':'2026-11-02T00:00:30Z',
            'run_id':'test-run','actor_id':'planner','call_id':'submit-1','causal_refs':['obs-e1','submit-1'],
            'text':'REVIEW_ONLY synthetic paper proposal; quote observation 2540 USD. No trade authority.',
            'dependencies':[{'evidence_id':'e1','source_version':'1','status':'DECLARED'}],
            'dependency_completeness':'COMPLETE',
            'extracts':[{'id':'extract-1','evidence_id':'e1','source_version':'1','span':[start,start+4],
                         'quote':'2540','field':'observed_quote','value':'2540','unit':'USD'}]},
        'policy':{'id':'synthetic-quote-freshness','version':'1','max_age_seconds':60,
                  'required_capabilities':sorted(v.REQUIRED_CAPABILITIES)}}


def advance(original,when='2026-11-02T00:01:01Z'):
    result=copy.deepcopy(original)
    result['packet_id']='packet-later'
    result['proposal'].update(id='proposal-later',revision=2,as_of=when,created_at=when,call_id='submit-later')
    result['proposal']['causal_refs'].append('submit-later')
    result['context'].update(revision=2,observed_at=when)
    result['context']['event_refs'].append('submit-later')
    return result


def add_replacement(original,valid='2026-11-02T00:01:00Z',retrieved='2026-11-02T00:01:05Z'):
    result=copy.deepcopy(original)
    result['evidence'].append(evidence('e2','2','2560',valid,retrieved,['e1']))
    result['context']['event_refs'].append('obs-e2')
    return result


def refreshed(original):
    result=add_replacement(advance(original,'2026-11-02T00:01:05Z'))
    e2=result['evidence'][1];start=e2['content'].index('2560')
    result['proposal']['dependencies']=[{'evidence_id':'e2','source_version':'2','status':'DECLARED'}]
    result['proposal']['extracts']=[{'id':'extract-2','evidence_id':'e2','source_version':'2','span':[start,start+4],
                                  'quote':'2560','field':'observed_quote','value':'2560','unit':'USD'}]
    result['proposal']['text']='REVIEW_ONLY synthetic paper proposal; quote observation 2560 USD. No trade authority.'
    return result


class PrimitiveTests(unittest.TestCase):
    def test_half_open_expiry_exact_boundary(self):
        begin,end=v._expiry(T0,60)
        self.assertEqual((end-begin).total_seconds(),60)
        self.assertTrue(begin<=v._utc('2026-11-02T00:00:59.999999Z')<end)
        self.assertFalse(begin<=v._utc('2026-11-02T00:01:00Z')<end)
        self.assertFalse(begin<=v._utc('2026-11-02T00:01:01Z')<end)

    def test_explicit_valid_until_can_only_shorten_expiry(self):
        begin,end=v._expiry(T0,60,'2026-11-02T00:00:45Z')
        self.assertEqual(end-begin,timedelta(seconds=45))
        _,end=v._expiry(T0,60,'2026-11-02T00:02:00Z')
        self.assertEqual(end-begin,timedelta(seconds=60))

    def test_timestamp_precision_and_timezone_are_not_guessed(self):
        with self.assertRaises(v.MissingPrerequisite):v._utc(None)
        for value in ['2026-11-02','2026-11-02T00:00:00','invalid',True,'']:
            with self.subTest(value=value),self.assertRaises(v.InvalidBinding):v._utc(value)
        self.assertEqual(v._utc('2026-11-02T05:30:00+05:30'),v._utc(T0))

    def test_invalid_policy_threshold_never_yields_an_expiry(self):
        with self.assertRaises(v.MissingPrerequisite):v._expiry(T0,None)
        for value in [True,-1,'60',float('nan'),float('inf')]:
            with self.subTest(value=value),self.assertRaises(v.InvalidBinding):v._expiry(T0,value)
        with self.assertRaises(v.InvalidBinding):v._expiry(T0,60,T0)
        begin,end=v._expiry(T0,0)
        self.assertEqual(begin,end)

    def test_scalar_grammar_does_not_turn_missingness_into_zero(self):
        self.assertEqual(v._scalar('2,540'),Decimal('2540'))
        with self.assertRaises(v.MissingPrerequisite):v._scalar(None)
        for value in ['NO_DATA','NaN','Infinity','2,54','2540 USD',True,2540]:
            with self.subTest(value=value),self.assertRaises(v.InvalidBinding):v._scalar(value)


class AssessmentTests(unittest.TestCase):
    def assertBlocked(self,p,status=None,code=None):
        assessment=v.assess(p)
        self.assertIsNone(assessment['clearance'])
        self.assertNotEqual(assessment['required_response']['action'],'none')
        if status:self.assertEqual(assessment['status'],status)
        if code:self.assertIn(code,[f['reason_code'] for f in assessment['findings']])
        return assessment

    def test_initial_packet_and_deterministic_assessment_are_pass(self):
        p=packet();c.require_valid_packet(p)
        original=copy.deepcopy(p)
        a=v.assess(p)
        self.assertEqual(a['status'],'PASS')
        self.assertEqual(a['packet_id'],p['packet_id'])
        self.assertTrue(all(f['status']=='PASS' for f in a['findings'] if f['required']))
        self.assertEqual(a,v.assess(p))
        self.assertEqual(p,original)
        self.assertTrue(v.validate_clearance(a['clearance'],p))

    def test_expiry_exact_boundary(self):
        before=advance(packet(),'2026-11-02T00:00:59.999999Z')
        self.assertEqual(v.assess(before)['status'],'PASS')
        for when in ['2026-11-02T00:01:00Z','2026-11-02T00:01:01Z']:
            with self.subTest(when=when):self.assertBlocked(advance(packet(),when),'FAIL','EVIDENCE_EXPIRED')

    def test_retrieval_cannot_reset_valid_time(self):
        p=advance(packet());ev=p['evidence'][0]
        ev['retrieved_at']=ev['recorded_at']=p['proposal']['as_of']
        self.assertBlocked(p,'FAIL','EVIDENCE_EXPIRED')

    def test_fake_new_valid_time_disagrees_with_source_text(self):
        p=advance(packet());ev=p['evidence'][0]
        ev['valid_at']=ev['retrieved_at']=ev['recorded_at']=p['proposal']['as_of']
        self.assertBlocked(p,'FAIL','VALID_TIME_TEXT_MISMATCH')

    def test_future_context_evidence_is_not_a_historical_supersession_witness(self):
        p=add_replacement(packet())
        a=self.assertBlocked(p,'FAIL','FUTURE_OR_MISORDERED_EVIDENCE')
        supers=[f for f in a['findings'] if f['obligation']=='known_supersession']
        self.assertEqual(supers[0]['status'],'PASS')
        self.assertEqual(supers[0]['observed']['visible_superseders'],[])

    def test_future_cited_observation_fails(self):
        p=refreshed(packet());p['proposal']['as_of']=p['proposal']['created_at']=p['context']['observed_at']='2026-11-02T00:00:30Z'
        self.assertBlocked(p,'FAIL','EVIDENCE_NOT_YET_VALID')

    def test_known_replacement_blocks_even_still_fresh_prior(self):
        p=add_replacement(packet(),'2026-11-02T00:00:20Z','2026-11-02T00:00:25Z')
        a=self.assertBlocked(p,'FAIL','KNOWN_SUPERSEDED_VERSION')
        fresh=[f for f in a['findings'] if f['obligation']=='freshness']
        self.assertEqual(fresh[0]['status'],'PASS')

    def test_cross_source_supersession_is_invalid_binding(self):
        p=add_replacement(packet(),'2026-11-02T00:00:20Z','2026-11-02T00:00:25Z')
        p['evidence'][1]['source_id']='other-source'
        self.assertBlocked(p,'ERROR','SUPERSESSION_SOURCE_BINDING_INVALID')

    def test_old_uncited_history_does_not_block_refreshed_dependency(self):
        p=refreshed(packet());a=v.assess(p)
        self.assertEqual(a['status'],'PASS')
        fresh=[f for f in a['findings'] if f['obligation']=='freshness']
        self.assertEqual(len(fresh),1)
        self.assertEqual(fresh[0]['subject']['evidence_id'],'e2')
        self.assertTrue(v.validate_clearance(a['clearance'],p))

    def test_wrong_value_and_version_detected_independently(self):
        p=packet();p['proposal']['extracts'][0]['value']='9999'
        self.assertBlocked(p,'FAIL','EXTRACT_VALUE_MISMATCH')
        p=packet();p['proposal']['extracts'][0]['source_version']='2'
        self.assertBlocked(p,'FAIL','EXTRACT_SOURCE_VERSION_MISMATCH')
        p=packet();p['proposal']['dependencies'][0]['source_version']='2'
        self.assertBlocked(p,'FAIL','DEPENDENCY_VERSION_MISMATCH')

    def test_wrong_quote_and_pointer_span_do_not_pass(self):
        p=packet();p['proposal']['extracts'][0]['quote']='9999'
        self.assertBlocked(p,'FAIL','EXTRACT_QUOTE_OR_SPAN_MISMATCH')
        p=packet();p['proposal']['extracts'][0]['span'][0]+=1
        self.assertBlocked(p,'FAIL','EXTRACT_QUOTE_OR_SPAN_MISMATCH')
        p=packet();p['evidence'][0]['pointer']['span']=[0,3]
        self.assertBlocked(p,'FAIL','EXTRACT_QUOTE_OR_SPAN_MISMATCH')

    def test_bad_digest_and_out_of_range_span_are_typed_errors(self):
        p=packet();p['evidence'][0]['content_digest']='0'*64
        self.assertBlocked(p,'ERROR','INVALID_PACKET_BINDING')
        p=packet();p['proposal']['extracts'][0]['span']=[0,10000]
        self.assertBlocked(p,'ERROR','INVALID_PACKET_BINDING')

    def test_missing_clocks_and_capture_are_inconclusive(self):
        for target,key in [('proposal','as_of'),('proposal','created_at'),('context','observed_at'),('evidence','valid_at'),('evidence','retrieved_at'),('evidence','recorded_at')]:
            with self.subTest(target=target,key=key):
                p=packet();obj=p[target][0] if target=='evidence' else p[target];obj[key]=None
                self.assertBlocked(p,'INCONCLUSIVE')
        for state in ['UNKNOWN','NOT_CAPTURED']:
            p=packet();p['capabilities'][0]['state']=state
            self.assertBlocked(p,'INCONCLUSIVE','CAPTURE_UNKNOWN_OR_UNAVAILABLE')
        p=packet();p['capabilities'].pop()
        self.assertBlocked(p,'INCONCLUSIVE','CAPTURE_UNKNOWN_OR_UNAVAILABLE')

    def test_missing_or_provisional_dependencies_do_not_clear(self):
        for value in [None,[]]:
            p=packet();p['proposal']['dependencies']=value
            self.assertBlocked(p,'INCONCLUSIVE')
        for value in ['PARTIAL','UNKNOWN']:
            p=packet();p['proposal']['dependency_completeness']=value
            self.assertBlocked(p,'INCONCLUSIVE')
        p=packet();p['proposal']['dependencies'][0]['status']='PROVISIONAL'
        self.assertBlocked(p,'INCONCLUSIVE','DEPENDENCY_PROVISIONAL')
        p=packet();p['proposal']['dependencies'][0]['evidence_id']='absent'
        self.assertBlocked(p,'INCONCLUSIVE','DEPENDENCY_EVIDENCE_MISSING')
        p=packet();p['proposal']['extracts']=[]
        self.assertBlocked(p,'INCONCLUSIVE','DEPENDENCY_COVERAGE_INCOMPLETE_OR_OUTSIDE_MAPPING')

    def test_unknown_field_unit_nodata_and_proposal_mapping_abstain(self):
        p=packet();p['proposal']['extracts'][0]['field']='market_outlook'
        self.assertBlocked(p,'INCONCLUSIVE','AUTHORED_MAPPING_UNRESOLVED')
        p=packet();p['proposal']['extracts'][0]['unit']=None
        self.assertBlocked(p,'INCONCLUSIVE','EXTRACT_UNIT_MISSING')
        p=packet();p['proposal']['extracts'][0]['unit']='EUR'
        self.assertBlocked(p,'FAIL','EXTRACT_UNIT_MISMATCH')
        p=packet();p['evidence'][0]['status']='NO_DATA'
        self.assertBlocked(p,'INCONCLUSIVE','NO_DATA_NOT_AN_OBSERVATION')
        p=packet();p['proposal']['text']='Hold because another analyst says so.'
        self.assertBlocked(p,'INCONCLUSIVE','PROPOSAL_EXTRACT_MAPPING_UNRESOLVED')

    def test_unknown_policy_fields_and_weakened_capture_policy_abstain(self):
        p=packet();p['policy']['allow_expired']=True
        self.assertBlocked(p,'INCONCLUSIVE','POLICY_OBLIGATIONS_NOT_IMPLEMENTED')
        p=packet();p['policy']['required_capabilities']=[]
        self.assertBlocked(p,'INCONCLUSIVE','POLICY_OBLIGATIONS_NOT_IMPLEMENTED')

    def test_expiry_overflow_is_typed_error_not_uncaught_exception(self):
        for threshold in [10**30,10**300]:
            p=packet();p['policy']['max_age_seconds']=threshold
            self.assertBlocked(p,'ERROR','MAX_AGE_OVERFLOW')
        p=packet();p['policy']['max_age_seconds']=0
        self.assertBlocked(p,'FAIL','EVIDENCE_EXPIRED')

    def test_invalid_packets_always_return_error_without_clearance(self):
        for p in [None,[],{}, {'packet_id':float('nan')}, {'packet_id':{}}]:
            with self.subTest(packet=p):self.assertBlocked(p,'ERROR','INVALID_PACKET_BINDING')
        p=packet();p['proposal']['as_of']='2026-11-02'
        self.assertBlocked(p,'ERROR','INVALID_PACKET_BINDING')

    def test_clearance_cannot_be_reused_after_any_bound_input_change(self):
        p=packet();clearance=v.assess(p)['clearance']
        mutations=[
            lambda x:x.update(packet_id='different'),
            lambda x:x['context'].update(revision=2),
            lambda x:x['context']['event_refs'].append('later-event'),
            lambda x:x['proposal'].update(revision=2),
            lambda x:x['proposal'].update(text='changed proposal'),
            lambda x:x['policy'].update(version='2'),
            lambda x:x['policy'].update(max_age_seconds=120),
            lambda x:x['evidence'][0].update(source_version='2'),
            lambda x:x['evidence'][0]['pointer'].update(uri='fixture://different'),
            lambda x:x['capabilities'][0].update(detail='different capture declaration'),
            lambda x:x['proposal'].update(as_of='2026-11-02T00:00:31Z'),
        ]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                changed=copy.deepcopy(p);mutate(changed)
                self.assertFalse(v.validate_clearance(clearance,changed))
        self.assertTrue(v.validate_clearance(clearance,p))
        self.assertFalse(v.validate_clearance(clearance,advance(p)))

    def test_tampered_or_forged_clearance_cannot_bypass_current_failure(self):
        p=packet();clearance=v.assess(p)['clearance']
        bad=copy.deepcopy(clearance);bad['required_finding_ids']=[]
        self.assertFalse(v.validate_clearance(bad,p))
        later=advance(p);forged=copy.deepcopy(clearance);forged['binding']=c.clearance_binding(later)
        self.assertFalse(v.validate_clearance(forged,later))
        self.assertFalse(v.validate_clearance(None,p))

    def test_assessment_outputs_are_detached_and_do_not_fake_host_events(self):
        p=packet();a=v.assess(p);original=copy.deepcopy(a)
        a['binding']['packet_id']='mutated-output'
        self.assertEqual(v.assess(p),original)
        blocked=v.assess(advance(p))
        self.assertTrue(blocked['required_response']['host_response_not_executed_by_verifier'])
        self.assertNotIn('events',blocked)


if __name__=='__main__':
    unittest.main()
