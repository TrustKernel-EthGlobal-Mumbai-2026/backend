import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from trustkernel.runner import ROOT
from trustkernel.trace import Observer, Redactor, Trace, rebuild, plain
from trustkernel.safety import Budget


class Contracts(unittest.TestCase):
    def test_schema_class_callback_serialization(self):
        from pydantic import BaseModel
        class Example(BaseModel):
            field: str
        self.assertIn('schema', plain(Example))
        self.assertEqual(plain(Example(field='value')), {'field':'value'})

    def test_llm_result_serialization_keeps_usage_and_tool_calls(self):
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import LLMResult, ChatGeneration
        msg = AIMessage(content='observable output',
                        tool_calls=[dict(name='get_news', args={}, id='tool-1', type='tool_call')],
                        usage_metadata=dict(input_tokens=10, output_tokens=5, total_tokens=15))
        result = plain(LLMResult(generations=[[ChatGeneration(message=msg)]]))
        saved = result['generations'][0][0]['message']
        self.assertEqual(saved['usage_metadata']['total_tokens'], 15)
        self.assertEqual(saved['tool_calls'][0]['name'], 'get_news')

    def test_real_responses_shape_normalized_without_network(self):
        import httpx
        from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI
        response = dict(id='resp_local_mock', object='response', created_at=0,
                        model='gpt-6.1-sol', status='completed',
                        output=[dict(id='msg_local', type='message', status='completed', role='assistant',
                                     content=[dict(type='output_text', text='Research only.', annotations=[])])],
                        usage=dict(input_tokens=10, output_tokens=5, total_tokens=15,
                                   input_tokens_details=dict(cached_tokens=0), output_tokens_details=dict(reasoning_tokens=0)))
        client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200,json=response)))
        with client:
            model = NormalizedChatOpenAI(model='gpt-6.1-sol', api_key='offline-test-placeholder',
                                         use_responses_api=True, max_retries=0, http_client=client)
            msg = model.invoke('Mock transport test')
            self.assertEqual(msg.content, 'Research only.')
            self.assertEqual(msg.usage_metadata['total_tokens'],15)

    def test_redaction_nested_and_free_text(self):
        with patch.dict(os.environ, {'TEST_API_KEY': 'distinctive-secret-12345'}):
            value = Redactor().clean({'authorization': 'abc', 'messages': [
                'Bearer abc123 https://u:p@example.test/path?api_key=abc&x=1 distinctive-secret-12345'],
                'encrypted_content': 'private', 'private_key': 'private'})
        text = json.dumps(value)
        for secret in ['abc123', 'u:p@', 'api_key=abc', 'distinctive-secret-12345', '"private"']:
            self.assertNotIn(secret, text)
        self.assertIn('REDACTED', text)

    def test_jsonl_rebuild_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            trace = Trace(Path(temp)/'run', 'test', {'mode': 'offline'})
            trace.emit('one', {'full': 'x'*10000})
            trace.emit('two', {'secret': 'never-store'})
            trace.close()
            raw = Path(temp)/'run/trace.jsonl'
            rebuild(raw, Path(temp)/'rebuilt.sqlite')
            with contextlib.closing(sqlite3.connect(Path(temp)/'rebuilt.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 2)
            raw.write_text(raw.read_text().replace('10000-not-present', 'x').replace('"one"', '"tampered"'))
            with self.assertRaises(ValueError):
                rebuild(raw, Path(temp)/'invalid.sqlite')

    def test_error_callbacks_and_parent_relationships(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            trace = Trace(Path(temp)/'run', 'test', {})
            observer = Observer(trace)
            for method in (observer.on_llm_error, observer.on_tool_error, observer.on_chain_error):
                method(RuntimeError('controlled failure'), run_id='child', parent_run_id='parent')
            trace.close()
            events = [json.loads(x) for x in (Path(temp)/'run/trace.jsonl').read_text().splitlines()]
            self.assertEqual({e['kind'] for e in events}, {'llm.error','tool.error','step.error'})
            self.assertTrue(all(e['parent_id'] == 'parent' and e['span_id'] == 'child' for e in events))

    def test_budget_denies_before_spending_and_stop(self):
        class Sink:
            def emit(self, *a, **kw):
                pass
        with tempfile.TemporaryDirectory() as temp:
            budget = Budget(Path(temp)/'budget.sqlite', .001, 'gpt-6.1-sol', time.time()+60, Path(temp)/'STOP', Sink())
            with self.assertRaises(PermissionError):
                budget.before(['safe request'], {})
            budget.limit = 1
            budget.before(['safe request'], {})
            Path(temp,'STOP').touch()
            with self.assertRaises(PermissionError):
                budget.before(['safe request'], {})

    def test_network_and_subprocess_denied_offline(self):
        script = '''from trustkernel.safety import network_guard
import socket,subprocess
network_guard(False)
for action in [lambda: socket.create_connection(('example.com',443)),lambda: subprocess.run(['whoami'])]:
 try: action()
 except PermissionError: continue
 raise AssertionError('Guard failed')
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_staged_budget_extends_once_and_persists_hard_stop(self):
        class Sink:
            def __init__(self):
                self.events = []
            def emit(self, kind, data):
                self.events.append((kind, data))
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            sink = Sink()
            path = Path(temp)/'cumulative.sqlite'
            def create():
                return Budget(path, 5, 'gpt-6.1-sol', time.time()+60, Path(temp)/'STOP', sink, 100, initial_limit=3)
            first = create()
            before_extension = int(3/first.reserve)
            maximum = int(5/first.reserve)
            for _ in range(before_extension):
                first.before(['request'], {})
            self.assertNotIn('budget.extended', [kind for kind, _ in sink.events])
            first.before(['request crossing initial allowance'], {})
            self.assertEqual([kind for kind, _ in sink.events].count('budget.extended'), 1)
            restarted = create()
            for _ in range(maximum-before_extension-1):
                restarted.before(['continued request'], {})
            with self.assertRaises(PermissionError):
                restarted.before(['would exceed five dollars'], {})
            with contextlib.closing(sqlite3.connect(path)) as db:
                reserved = db.execute('SELECT reserved FROM budget').fetchone()[0]
                self.assertLessEqual(reserved, 5)
                self.assertAlmostEqual(reserved, first.reserve*maximum)
                self.assertEqual(db.execute('SELECT active_limit FROM budget_policy').fetchone()[0], 5)
            self.assertEqual([kind for kind, _ in sink.events].count('budget.extended'), 1)
            with self.assertRaises(PermissionError):
                Budget(path, 6, 'gpt-6.1-sol', time.time()+60, Path(temp)/'STOP', sink, initial_limit=3)

    def test_usage_settlement_releases_only_known_usage_once(self):
        class Sink:
            def emit(self,*a,**kw):
                pass
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'budget.sqlite'
            budget=Budget(path,5,'gpt-6.1-sol',time.time()+60,Path(temp)/'STOP',Sink(),initial_limit=3)
            budget.before(['prompt'],{'run_id':'span-1'})
            response=dict(generations=[[dict(message=dict(id='resp-test',usage_metadata=dict(input_tokens=10,output_tokens=5,total_tokens=15)))]])
            budget.settle(response,{'run_id':'span-1'})
            budget.settle(response,{'run_id':'span-1'})
            with contextlib.closing(sqlite3.connect(path)) as db:
                self.assertAlmostEqual(db.execute('SELECT reserved FROM budget').fetchone()[0],.0001)
            budget.before(['another prompt'],{'run_id':'span-2'})
            budget.settle({}, {'run_id':'span-2'})
            with contextlib.closing(sqlite3.connect(path)) as db:
                self.assertAlmostEqual(db.execute('SELECT reserved FROM budget').fetchone()[0],.0001+budget.reserve)

    def test_parallel_reservations_cannot_overshoot_shared_ceiling(self):
        from concurrent.futures import ThreadPoolExecutor
        class Sink:
            def emit(self,*a,**kw):
                pass
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'shared.sqlite'
            budgets=[Budget(path,.5,'gpt-6.1-sol',time.time()+60,Path(temp)/'STOP',Sink()) for _ in range(2)]
            def reserve(pair):
                index,budget=pair
                try:
                    budget.before(['prompt'],{'run_id':str(index)})
                    return True
                except PermissionError:
                    return False
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes=list(pool.map(reserve,enumerate(budgets)))
            self.assertEqual(sum(outcomes),1)
            with contextlib.closing(sqlite3.connect(path)) as db:
                self.assertAlmostEqual(db.execute('SELECT reserved FROM budget').fetchone()[0],budgets[0].reserve)

    def test_legacy_budget_reconciliation_is_audited_and_idempotent(self):
        from trustkernel.reconcile_budget import reconcile
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            base=Path(temp)
            trace=Trace(base/'session'/'sol-test','test',{'mode':'paid','model':'gpt-6.1-sol'})
            trace.emit('run.start',{})
            trace.emit('llm.start',{},span_id='span')
            trace.emit('budget.reserved',{'reserved_usd':.14048})
            trace.emit('llm.end',{'response':{'generations':[[{'message':{'id':'response-test','usage_metadata':{'input_tokens':10,'output_tokens':5}}}]]}},span_id='span')
            trace.close()
            with contextlib.closing(sqlite3.connect(base/'approved-budget.sqlite')) as db,db:
                db.execute('CREATE TABLE budget(id INTEGER PRIMARY KEY,reserved REAL)')
                db.execute('INSERT INTO budget VALUES (1,.14048)')
            audit=reconcile(base)
            self.assertAlmostEqual(audit['committed_upper_usd'],.0001)
            self.assertEqual(audit['requests'],1)
            self.assertEqual(reconcile(base),audit)

    def test_thirty_minute_schedule_and_explicit_gate(self):
        from trustkernel.window import schedule
        self.assertEqual(schedule(),[0,600,1200])
        with self.assertRaises(ValueError):
            schedule(10800)
        result=subprocess.run([sys.executable,'-m','trustkernel.window'],cwd=ROOT,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('authorization',result.stderr)

    def test_descriptive_analysis_reconciles_completed_paid_pair(self):
        from trustkernel.analysis import analyze_session
        session=ROOT/'runs/20261030-004541-47fb5560'
        if not session.exists():
            self.skipTest('Recorded paid fixture not present in this checkout')
        result=analyze_session(session)
        self.assertEqual(len(result['runs']),2)
        self.assertTrue(result['pairs'][0]['identical_available_fixture'])
        self.assertTrue(result['pairs'][0]['both_completed'])
        self.assertAlmostEqual(result['total_estimated_standard_cost_usd'],.233855)
        self.assertTrue(all(r['usage_calls']==13 for r in result['runs']))

    def test_launch_gates(self):
        for args in [['--mode','paid'], ['--hours','3'], ['--mode','paid','--approve-paid','--budget-usd','NaN']]:
            result = subprocess.run([sys.executable,'-m','trustkernel.experiment',*args], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('error:', result.stderr)

    def test_installed_sdk_responses_request_configuration_without_network(self):
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model='gpt-6.1-sol', api_key='offline-test-placeholder',
                         base_url='https://api.openai.com/v1', use_responses_api=True,
                         reasoning_effort='medium', store=False, service_tier='default',
                         max_tokens=2048, max_retries=0, timeout=60)
        payload = llm._get_request_payload('Read-only research configuration test')
        self.assertEqual(payload['model'], 'gpt-6.1-sol')
        self.assertEqual(payload['reasoning']['effort'], 'medium')
        self.assertEqual(payload['max_output_tokens'], 2048)
        self.assertFalse(payload['store'])

    @unittest.skipUnless(os.name == 'nt', 'Windows process tree containment')
    def test_windows_deadline_stops_venv_process_tree(self):
        import ctypes
        from trustkernel.experiment import terminate_research_child
        with tempfile.TemporaryDirectory() as temp:
            pidfile = Path(temp)/'child.pid'
            script = 'import subprocess,sys,time,pathlib; child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);pathlib.Path(sys.argv[1]).write_text(str(child.pid));time.sleep(30)'
            process = subprocess.Popen([sys.executable,'-c',script,str(pidfile)], cwd=ROOT)
            try:
                deadline = time.time()+5
                while not pidfile.exists() and time.time()<deadline:
                    time.sleep(.05)
                self.assertTrue(pidfile.exists())
                child_pid = int(pidfile.read_text())
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.OpenProcess.restype = ctypes.c_void_p
                kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                handle = kernel.OpenProcess(0x100000, False, child_pid)
                self.assertTrue(handle)
                try:
                    terminate_research_child(process)
                    self.assertEqual(kernel.WaitForSingleObject(handle,2000), 0)
                finally:
                    kernel.CloseHandle(handle)
            finally:
                if process.poll() is None:
                    terminate_research_child(process)

    def test_recent_offline_pair_full_graph_coverage(self):
        sessions = sorted((ROOT/'runs').glob('*/experiment.json'))
        sessions = [p for p in sessions if json.loads(p.read_text())['mode'] == 'offline' and json.loads(p.read_text())['status'] == 'success']
        self.assertTrue(sessions, 'Run offline smoke before contract suite')
        session = sessions[-1].parent
        hashes = []
        for arm in ['sol','terra']:
            directory = next(session.glob(arm+'-*'))
            events = [json.loads(x) for x in (directory/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
            counts = {}
            for event in events:
                counts[event['kind']] = counts.get(event['kind'],0)+1
            for kind in ['llm.start','llm.end','tool.start','tool.end','evidence.available','evidence.retrieved','decision.paper','run.end']:
                self.assertGreater(counts.get(kind,0), 0, kind)
            self.assertEqual(counts['tool.end'], 7)
            self.assertEqual(counts['llm.start'], counts['llm.end'])
            self.assertEqual(events[0]['context']['inference'], 'scripted-test-double')
            hashes.append(events[0]['context']['fixture_hash'])
            final = json.loads((directory/'final_state.json').read_text(encoding='utf-8'))
            self.assertTrue(final['final_trade_decision'])
            self.assertTrue(final['investment_plan'])
            self.assertGreater(len(json.loads((directory/'claim_candidates.json').read_text())), 0)
        self.assertEqual(*hashes)


if __name__ == '__main__':
    unittest.main()
