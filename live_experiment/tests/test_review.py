"""Offline trace/source/budget doubles only; no provider or model imports."""
from contextlib import closing
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from live_experiment import review as r


class TraceDouble:
    def __init__(self,directory,arm='sol',pair='pair-0'):
        self.path=Path(directory);self.path.mkdir()
        self.events=[]
        self.context={'arm':arm,'model':'offline-test-'+arm,'pair_id':pair,
            'source_mode':'live_native_market_sources','mode':'live_native_market_sources','inference':'offline_trace_double'}
        self.manifest={'status':'running','context':self.context,'config':{'max_tool_rounds':2}}
        self.emit('run.start',self.manifest)

    def emit(self,kind,payload,span=None,actor=None):
        p=copy.deepcopy(payload)
        if actor:p.setdefault('metadata',{}).setdefault('metadata',{})['langgraph_checkpoint_ns']=actor+':test|wrap_up:test'
        e={'schema_version':1,'seq':len(self.events)+1,'event_id':'event-'+str(len(self.events)+1),'run_id':self.path.name,
            'timestamp':(datetime(2026,11,3,tzinfo=timezone.utc)+timedelta(seconds=len(self.events))).isoformat(),
            'kind':kind,'span_id':span,'parent_id':None,'payload':p,'context':copy.deepcopy(self.context),
            'previous_hash':self.events[-1]['event_hash'] if self.events else None}
        e['event_hash']=r._hash(e);self.events.append(e);return e

    def source(self,content='provider close=100',status='AVAILABLE',times=None,tool='get_verified_market_snapshot'):
        return self.emit('evidence.retrieved',{'evidence_id':'live-'+str(len(self.events)),'tool':tool,'request':{'symbol':'ETH-USD'},
            'provider':'yfinance','source_status':status,'content':content,'content_hash':r._text_hash(content),
            'requested_at':'2026-11-03T00:00:00Z','retrieved_at':'2026-11-03T00:00:01Z',
            'source_urls':['https://query1.finance.yahoo.com/v8/finance/chart/ETH-USD?token=hidden'],
            'http_ids':['http-1'],'source_time_fields':times or [],'cache_status':'network_observed','cache_files':[]})

    def market(self,content='provider close=100',invoked=True,usage=True,settled=True,source_status='AVAILABLE'):
        if invoked:self.emit('tool.start',{'tool':{'name':'get_verified_market_snapshot'}},'tool-1','Market Analyst')
        source=self.source(content,source_status)
        instruction='Before writing the final report, call get_verified_market_snapshot for this ticker. You have no tools; your tool rounds are spent.'
        self.emit('llm.start',{'messages':[[{'type':'system','content':instruction},{'type':'tool','content':content,'tool_call_id':'tc1'}]]},'call-1','Market Analyst')
        self.emit('budget.reserved',{'request_id':'req-'+self.path.name,'reserved_usd':0.32})
        message={'response_metadata':{'id':'resp-'+self.path.name},'tool_calls':[]}
        if usage:message['usage_metadata']={'input_tokens':100,'output_tokens':20}
        self.report='Market report: source status '+source_status
        self.emit('llm.end',{'response':{'generations':[[{'text':self.report,'message':message}]]}},'call-1')
        if settled:self.emit('budget.settled',{'request_id':'req-'+self.path.name,'response_id':'resp-'+self.path.name,
            'charged_upper_usd':0.001,'usage':{'input_tokens':100,'output_tokens':20}})
        else:self.emit('budget.usage_unknown',{'request_id':'req-'+self.path.name,'full_reservation_retained':True})
        return source

    def finish(self,failed=False):
        if failed:self.emit('run.error',{'error_type':'ConnectionError','error':'offline stub failure'})
        else:self.emit('run.end',{'status':'success'})
        self.manifest.update(status='failed' if failed else 'success',ended_at='2026-11-03T00:01:00Z')

    def save(self,index_count=None,tail=b'',final=True):
        (self.path/'run_manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')
        (self.path/'trace.jsonl').write_bytes(b''.join((json.dumps(e,ensure_ascii=False)+'\n').encode('utf-8') for e in self.events)+tail)
        with closing(sqlite3.connect(self.path/'trace.sqlite')) as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY,event_id TEXT,run_id TEXT,timestamp TEXT,kind TEXT,span_id TEXT,parent_id TEXT,payload_json TEXT,event_hash TEXT)')
            db.execute('DELETE FROM events')
            selected=self.events if index_count is None else self.events[:index_count]
            for e in selected:db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',(e['seq'],e['event_id'],e['run_id'],e['timestamp'],e['kind'],e['span_id'],e['parent_id'],json.dumps(e['payload']),e['event_hash']))
            db.commit()
        if final and hasattr(self,'report'):
            (self.path/'final_state.json').write_text(json.dumps({'market_report':self.report,'final_trade_decision':'**Rating**: Hold'}),encoding='utf-8')


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='live-review-test-')
        self.root=Path(self.temp.name);self.session=self.root/'live-session';self.session.mkdir()
        self.budget=self.root/'budget.sqlite'
        with closing(sqlite3.connect(self.budget)) as db:
            db.executescript('CREATE TABLE budget(id INTEGER PRIMARY KEY,reserved REAL);CREATE TABLE budget_policy(id INTEGER PRIMARY KEY,initial_limit REAL,active_limit REAL,hard_limit REAL);CREATE TABLE requests(id TEXT PRIMARY KEY,reserved REAL,charge REAL,status TEXT,response_id TEXT);')
            db.execute('INSERT INTO budget VALUES(1,1.8376825)');db.execute('INSERT INTO budget_policy VALUES(1,3,3,5)')
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',('older-unknown',0.16024,None,'in_flight_or_unknown',None));db.commit()
        self.meta={'mode':'paid_live_native_sources','source_mode':'live_native','status':'running','budget_ledger':str(self.budget),'review_test_stub':True,'pairs':[{'pair_id':'pair-0','arms':[]}]}
        self.save_meta()

    def tearDown(self):self.temp.cleanup()
    def save_meta(self):(self.session/'experiment.json').write_text(json.dumps(self.meta),encoding='utf-8')
    def analyze(self):return r.analyze_session(self.session)

    def test_live_success_exact_integrity_source_exposure_and_protocol(self):
        t=TraceDouble(self.session/'sol-test');t.market();t.finish();t.save()
        result=self.analyze();row=result['runs'][0]
        self.assertEqual(row['status'],'success');self.assertEqual(row['trace_integrity']['status'],'PASS')
        self.assertEqual(row['trace_integrity']['sqlite_status'],'EXACT_PARITY')
        self.assertEqual(row['protocol']['status'],'PASS');self.assertTrue(row['protocol']['tool_rounds_spent_message_observed'])
        self.assertEqual(row['input_tokens'],100);self.assertEqual(row['output_tokens'],20)
        self.assertEqual(row['charges']['known_charged_upper_usd'],0.001)
        source=row['sources'][0];self.assertTrue(source['input_exposures'])
        self.assertNotIn('hidden',source['source_urls'][0]);self.assertEqual(source['source_time_precision'],'UNKNOWN')
        self.assertIsNone(result['total_estimated_standard_cost_usd'])
        self.assertTrue((self.session/'analysis.md').exists());self.assertTrue((self.session/'review_packets.json').exists())

    def test_called_but_source_failure_is_separate_from_tool_omission(self):
        t=TraceDouble(self.session/'sol-test');t.market(content='DATA_UNAVAILABLE: native provider failed',source_status='SOURCE_UNAVAILABLE');t.finish();t.save()
        row=self.analyze()['runs'][0]
        self.assertEqual(row['protocol']['status'],'PASS')
        self.assertEqual(row['protocol']['source_result_statuses'],['SOURCE_UNAVAILABLE'])
        self.assertEqual(row['source_failures'],1)
        t2=TraceDouble(self.session/'terra-test','terra');t2.market(invoked=False);t2.finish();t2.save()
        row=next(x for x in self.analyze()['runs'] if x['arm']=='terra')
        self.assertEqual(row['protocol']['status'],'FAIL')
        self.assertEqual(row['protocol']['reason'],'REQUIRED_CALL_OMITTED')
        self.assertTrue(row['protocol']['tool_rounds_spent_message_observed'])

    def test_no_usage_is_unknown_and_reservation_is_retained(self):
        t=TraceDouble(self.session/'sol-test');t.market(usage=False,settled=False);t.finish();t.save()
        row=self.analyze()['runs'][0]
        self.assertIsNone(row['input_tokens']);self.assertIsNone(row['output_tokens'])
        self.assertEqual(len(row['usage']['completed_events_without_usage']),1)
        self.assertEqual(row['charges']['pending_requests'],1)
        self.assertEqual(row['charges']['known_pending_reservation_usd'],0.32)
        self.assertFalse(row['charges']['all_observed_reservations_settled'])

    def test_settlement_usage_recovers_only_matching_response_id(self):
        t=TraceDouble(self.session/'sol-test');t.market(usage=False,settled=True);t.finish();t.save()
        row=self.analyze()['runs'][0]
        self.assertEqual(row['input_tokens'],100)
        self.assertEqual(row['usage']['usage_records'][0]['identity_source'],'budget_settlement_response_id')
        self.assertEqual(row['usage']['completed_events_without_usage'],[])

    def test_distinct_concurrent_content_is_reported_without_equal_evidence_claim(self):
        for arm,value in [('sol','100'),('terra','101')]:
            t=TraceDouble(self.session/(arm+'-test'),arm);t.market(content='provider close='+value);t.finish();t.save()
        pair=self.analyze()['pairs'][0]
        self.assertTrue(pair['both_completed'])
        self.assertEqual(pair['differing_shared_source_requests'],1)
        self.assertIsNone(pair['consumed_evidence_equal']);self.assertIsNone(pair['identical_available_fixture'])

    def test_active_partial_tail_and_sqlite_lag_are_prefix_scoped(self):
        t=TraceDouble(self.session/'sol-test');t.emit('llm.start',{'messages':[]},'pending');t.save(index_count=1,tail=b'{"partial":',final=False)
        row=self.analyze()['runs'][0]
        self.assertEqual(row['trace_integrity']['status'],'PASS')
        self.assertEqual(row['trace_integrity']['scope'],'active_common_recorded_prefix')
        self.assertTrue(row['trace_integrity']['partial_last_line'])
        self.assertEqual(row['trace_integrity']['sqlite_status'],'ACTIVE_PREFIX_PARITY_WITH_LAG')
        self.assertEqual(row['pending_llm_count'],1);self.assertEqual(row['status'],'running')

    def test_closed_tail_count_and_hash_corruption_fail_integrity(self):
        t=TraceDouble(self.session/'sol-test');t.market();t.finish();t.save(index_count=len(t.events)-1)
        row=self.analyze()['runs'][0];self.assertEqual(row['trace_integrity']['status'],'ERROR')
        t.save(tail=b'{"partial":');row=self.analyze()['runs'][0]
        self.assertEqual(row['trace_integrity']['status'],'ERROR')
        t.save();raw=t.path/'trace.jsonl';events=copy.deepcopy(t.events);events[1]['payload']['changed']=True
        raw.write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf-8')
        row=self.analyze()['runs'][0];self.assertEqual(row['trace_integrity']['hashchain_status'],'ERROR')

    def test_complete_common_prefix_mismatch_is_not_excused_as_live_lag(self):
        t=TraceDouble(self.session/'sol-test');t.emit('llm.start',{'messages':[]},'pending');t.save(final=False)
        with closing(sqlite3.connect(t.path/'trace.sqlite')) as db:
            db.execute("UPDATE events SET payload_json='{}' WHERE seq=2");db.commit()
        row=self.analyze()['runs'][0]
        self.assertEqual(row['trace_integrity']['status'],'ERROR')
        self.assertEqual(row['trace_integrity']['sqlite_status'],'COMMON_PREFIX_MISMATCH')

    def test_error_partial_run_and_http_errors_remain_visible(self):
        t=TraceDouble(self.session/'sol-test');t.emit('source.http.start',{'http_id':'h1'})
        t.emit('source.http.error',{'http_id':'h1','error_type':'TimeoutError','url':'https://api.stlouisfed.org/fred/series?api_key=hidden'})
        t.emit('source.tool.start',{'evidence_id':'still-pending','tool':'get_global_news'})
        t.emit('source.tool.error',{'evidence_id':'failed','tool':'get_news','retrieved_at':'2026-11-03T00:00:00Z','error_type':'TimeoutError'})
        t.emit('llm.start',{'messages':[]},'failed-call');t.emit('llm.error',{'error_type':'ConnectionError'},'failed-call')
        t.emit('runtime.log',{'logger':'native-agent','message':'Structured output failed; fallback path attempted.'})
        t.finish(failed=True);t.save(final=False)
        row=self.analyze()['runs'][0]
        self.assertEqual(row['status'],'failed');self.assertEqual(row['llm_errors'],1)
        self.assertEqual(row['source_http_errors'],1);self.assertEqual(row['sources'][0]['status'],'ERROR')
        self.assertEqual(row['pending_llm_count'],0);self.assertEqual(row['protocol']['status'],'INCONCLUSIVE')
        self.assertEqual(row['source_tool_pending_ids'],['still-pending'])
        self.assertNotIn('hidden',row['http_observations'][1]['url'])
        self.assertEqual(len(row['runtime_fallback_messages']),1)

    def test_budget_read_is_nonmutating_and_preserves_older_unknown_hold(self):
        before=hashlib.sha256(self.budget.read_bytes()).hexdigest()
        result=self.analyze();budget=result['budget']
        self.assertEqual(budget['committed_upper_plus_holds_usd'],1.8376825)
        self.assertEqual(budget['pending_or_unknown_reserved_usd'],0.16024)
        self.assertTrue(budget['older_unknown_holds_not_released'])
        self.assertEqual(hashlib.sha256(self.budget.read_bytes()).hexdigest(),before)

    def test_missing_budget_and_incomplete_pair_are_explicit(self):
        self.meta['budget_ledger']=str(self.root/'absent.sqlite');self.save_meta()
        t=TraceDouble(self.session/'sol-test');t.save(final=False)
        result=self.analyze();self.assertEqual(result['budget']['status'],'INCONCLUSIVE')
        self.assertFalse(result['pairs'][0]['both_completed']);self.assertEqual(result['pairs'][0]['missing_arms'],['terra'])
        self.assertFalse((self.root/'absent.sqlite').exists())

    def test_source_status_missing_credential_nodata_withheld_are_not_available(self):
        t=TraceDouble(self.session/'sol-test')
        for status in ['MISSING_CREDENTIAL','NO_DATA','WITHHELD']:
            t.source(content=status,status=status,tool='get_prediction_markets')
        t.save(final=False)
        row=self.analyze()['runs'][0]
        self.assertEqual(set(row['source_statuses']),{'MISSING_CREDENTIAL','NO_DATA','WITHHELD'})
        self.assertNotIn('AVAILABLE',row['source_statuses'])

    def test_original_source_files_are_not_modified(self):
        t=TraceDouble(self.session/'sol-test');t.market();t.finish();t.save()
        files=[t.path/name for name in ['trace.jsonl','trace.sqlite','run_manifest.json','final_state.json']]
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        self.analyze();self.analyze()
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

    def test_historical_or_fixture_session_write_is_refused(self):
        self.meta['source_mode']='synthetic';self.meta['mode']='paid';self.save_meta()
        with self.assertRaises(ValueError):self.analyze()
        self.assertFalse((self.session/'analysis.json').exists())
        self.meta['source_mode']='live_native';self.save_meta();(self.session/'fixture.json').write_text('{}')
        with self.assertRaises(ValueError):self.analyze()


if __name__=='__main__':unittest.main()
