"""Offline negatives over disposable canonical doubles; never original traces."""
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from live_verification import rules as r
from live_verification import rules_checks as ck


SNAPSHOT = '''## Verified market data snapshot for TEST-USD
- Latest trading row used: 2026-01-01
### Latest verified OHLCV row
| Field | Value |
|---|---:|
| Open | 100.00 |
| High | 110.00 |
| Low | 90.00 |
| Close | 101.25 |
| Volume | 1000 |
### Verified technical indicators (latest row)
| Indicator | Value |
|---|---:|
| rsi | 33.0663 |
| atr | 78.8605 |
### Recent verified closes (last 1 rows)
| Date | Close |
|---|---:|
| 2026-01-01 | 101.25 |
'''


def stub(*, invoked=True, source_status='AVAILABLE', prompt=True, incomplete=False,
         report='Close 101.25; RSI 33.07. If identical rules hold, 96 - 74 = 22%.', actor='Market Analyst'):
    """Schema-shaped local rows; IDs are readable test-only identities."""
    rows = []
    def add(table, identity, **fields):
        row = dict(table=table, id=identity, run_id='offline-test-run', **fields)
        rows.append(row); return row
    def event(seq, kind, payload, checkpoint='Market Analyst:offline'):
        payload = copy.deepcopy(payload)
        if checkpoint:
            payload['metadata'] = {'metadata': {'langgraph_checkpoint_ns': checkpoint}}
        return add('events', 'event-'+str(seq), seq=seq, kind=kind, span_id='span-'+str(seq),
                   parent_id=None, timestamp='2026-01-01T00:00:00Z',
                   raw={'seq':seq, 'kind':kind, 'payload':payload})
    add('runs', 'run', context={'mode':'offline_test_stub'})
    event(1, 'run.start', {'config':{'max_tool_rounds':2}})
    event(2, 'tool.start' if invoked else 'step.start', {'tool':{'name':'get_verified_market_snapshot'}})
    body = SNAPSHOT if source_status == 'AVAILABLE' else 'DATA_UNAVAILABLE: provider failed'
    event(3, 'evidence.retrieved', {'tool':'get_verified_market_snapshot', 'content':body, 'source_status':source_status})
    event(4, 'runtime.log', {'message':'Tool rounds spent; fallback without tools'})
    instruction = ('Before writing the final report, call get_verified_market_snapshot. ' if prompt else '') + body
    event(5, 'llm.start', {'messages':[[{'content':instruction,'type':'human'}]]})
    event(6, 'llm.end', {'response':{'status':'incomplete' if incomplete else 'completed'}})
    add('calls', 'call', actor=actor, start_event_id='event-5', end_event_id='event-6', input_seq=5, output_seq=6, status='completed')
    add('texts', 'input', text=instruction, sha256=r.text_hash(instruction), event_id='event-5', pointer='/payload/messages/0/0/content',
        call_id='call', actor=actor, role='input', input_seq=5, output_seq=None)
    add('texts', 'output', text=report, sha256=r.text_hash(report), event_id='event-6', pointer='/payload/response/text',
        call_id='call', actor=actor, role='generated_narrative', input_seq=5, output_seq=6)
    add('reports', 'report', field='market_report', text_id='output', call_id='call', output_event_id='event-6', origin_status='bound')
    add('sources', 'source', content=body, sha256=r.text_hash(body), source_version=r.text_hash(body), tool='get_verified_market_snapshot',
        args={'symbol':'TEST-USD'}, source_status=source_status, provider='offline_test_stub', event_id='event-3', seq=3,
        retrieved_at='2026-01-01T00:00:00Z', pointer='/payload/content')
    at = instruction.index(body)
    add('exposures', 'exposure', call_id='call', text_id='input', source_id='source', start=at, end=at+len(body),
        quote=body, pre_assertion=True, retrieval_seq=3, mode='content_presence_only')
    add('candidates', 'candidate', text_id='output', start=0, end=len(report), quote=report, status='provisional')
    return rows


def selected(rows, rule):
    return [f for f in r.assess_rows(rows) if f['rule_id'] == rule]


class PureRuleTests(unittest.TestCase):
    def test_invocation_success_is_separate_from_source_failure(self):
        rows = stub(source_status='SOURCE_UNAVAILABLE')
        self.assertEqual(selected(rows, 'required_snapshot_invocation')[0]['status'], 'PASS')
        self.assertEqual(selected(rows, 'recorded_source_availability')[0]['status'], 'INCONCLUSIVE')

    def test_omission_fails_despite_fallback_and_acknowledgement(self):
        rows = stub(invoked=False, report='Snapshot was not run because no tool rounds remain.')
        f = selected(rows, 'required_snapshot_invocation')[0]
        self.assertEqual(f['status'], 'FAIL')
        context = selected(rows, 'tool_round_fallback_context')[0]
        self.assertEqual(context['observed']['max_tool_rounds'], 2)
        self.assertEqual(len(context['observed']['fallbacks']), 1)

    def test_missing_obligation_or_actor_is_inconclusive(self):
        self.assertEqual(selected(stub(prompt=False), 'required_snapshot_invocation')[0]['status'], 'INCONCLUSIVE')
        self.assertEqual(selected(stub(actor=None), 'required_snapshot_invocation')[0]['status'], 'INCONCLUSIVE')
        rows = stub(); rows = [row for row in rows if row['id'] != 'event-4']
        self.assertEqual(selected(rows, 'required_snapshot_invocation')[0]['status'], 'INCONCLUSIVE')

    def test_source_statuses_never_fall_back_to_available(self):
        for status in ('WITHHELD','NO_DATA','MISSING_CREDENTIAL','ERROR','UNKNOWN'):
            with self.subTest(status=status):
                row = selected(stub(source_status=status), 'recorded_source_availability')[0]
                self.assertEqual(row['status'], 'INCONCLUSIVE')
                self.assertEqual(row['observed']['status'], status)

    def test_ohlc_invalid_bounds_missing_and_unicode_spans(self):
        self.assertEqual(ck.ohlc({'Open':'2','High':'4','Low':'3','Close':'2.9'})[0], 'FAIL')
        self.assertEqual(ck.ohlc({'Open':'2'})[0], 'INCONCLUSIVE')
        text = '\u03bb\nDate,Open,High,Low,Close\n2026-01-01,100,110,102,101\n'
        bar = ck.bars(text)[0]
        self.assertEqual(text[bar['fields']['Close']['start']:bar['fields']['Close']['end']], '101')
        self.assertEqual(ck.ohlc({k:v['value'] for k,v in bar['fields'].items()})[0], 'FAIL')

    def test_conflict_subject_is_versions_not_report_and_symbols_bound(self):
        rows = stub(report='The CSV Close 100 differs from snapshot Close 101.25.')
        csv = 'Date,Open,High,Low,Close\n2026-01-01,100,110,90,100\n'
        rows.append(dict(rows[-3], id='csv-source', content=csv, sha256=r.text_hash(csv), source_version=r.text_hash(csv), tool='get_stock_data'))
        conflict = selected(rows, 'within_run_csv_snapshot_agreement')[0]
        self.assertEqual(conflict['status'], 'FAIL')
        self.assertIn('Close', conflict['observed']['differences'])
        scalars = selected(rows, 'selected_scalar_source_consistency')
        self.assertTrue(scalars)
        self.assertNotIn('FAIL', [f['status'] for f in scalars])
        rows[-1]['args'] = {'symbol':'OTHER-USD'}
        self.assertEqual(selected(rows, 'within_run_csv_snapshot_agreement'), [])

    def test_scalar_rounding_and_unmatched_number_are_bounded(self):
        rows = stub(report='RSI 33.07. ATR 78.86. Close 999.00.')
        checks = selected(rows, 'selected_scalar_source_consistency')
        self.assertEqual(sorted(f['status'] for f in checks), ['INCONCLUSIVE','PASS','PASS'])
        self.assertTrue(all(f['observed']['semantic_alignment'] == 'INCONCLUSIVE' for f in checks))
        for value in ('NaN','Inf','1e3',True,None):
            with self.assertRaises(ValueError): ck.decimal(value)
        self.assertEqual(ck.rounded_equal('1.01','1.005')[0], True)

    def test_no_hindsight_or_crossrun_source_numeric_pass(self):
        for change in ('after','crossrun','not_preassertion'):
            rows = stub(report='RSI 33.07')
            source = next(x for x in rows if x['table'] == 'sources')
            if change == 'after': source['seq'] = 7
            elif change == 'crossrun': source['run_id'] = 'other-run'
            else: next(x for x in rows if x['table'] == 'exposures')['pre_assertion'] = False
            self.assertEqual(selected(rows, 'selected_scalar_source_consistency')[0]['status'], 'INCONCLUSIVE')

    def test_conditional_arithmetic_keeps_full_context_and_unknown_assumptions(self):
        f = selected(stub(), 'selected_subtraction_arithmetic')[0]
        self.assertEqual(f['status'], 'PASS')
        self.assertTrue(f['observed']['condition_wording_observed'])
        self.assertEqual(f['observed']['settlement_alignment'], 'INCONCLUSIVE')
        self.assertTrue(any('If identical rules' in ref['quote'] for ref in f['span_refs']))
        self.assertEqual(ck.arithmetic('22 = 96 - 74')[0]['status'], 'PASS')
        self.assertEqual(ck.arithmetic('96 - 74 = 23')[0]['status'], 'FAIL')

    def test_urls_duplicate_and_citation_require_available_preinput_source(self):
        rows = stub(report='Article [one](https://example.test/story).')
        source = next(x for x in rows if x['table'] == 'sources')
        source['content'] += '\nhttps://example.test/story https://example.test/story\n'
        source['sha256'] = r.text_hash(source['content'])
        input_text = next(x for x in rows if x['id'] == 'input')
        input_text['text'] += '\nhttps://example.test/story https://example.test/story\n'
        input_text['sha256'] = r.text_hash(input_text['text'])
        exposure = next(x for x in rows if x['table'] == 'exposures')
        exposure.update(quote=source['content'], end=exposure['start']+len(source['content']))
        inventory = selected(rows, 'exact_url_duplicate_lineage')[0]
        self.assertEqual(inventory['observed']['repeated_occurrences'], 1)
        self.assertEqual(inventory['status'], 'PASS')
        citation = selected(rows, 'citation_preinput_provenance')[0]
        self.assertEqual(citation['status'], 'PASS')
        next(x for x in rows if x['table'] == 'exposures')['pre_assertion'] = False
        self.assertEqual(selected(rows, 'citation_preinput_provenance')[0]['status'], 'INCONCLUSIVE')

    def test_incomplete_and_unresolved_origin_are_not_workflow_clearance(self):
        self.assertEqual(selected(stub(incomplete=True), 'provider_response_completion')[0]['status'], 'FAIL')
        rows = stub(); report = next(x for x in rows if x['table'] == 'reports')
        report['call_id'] = None
        next(x for x in rows if x['id'] == 'output')['call_id'] = None
        self.assertEqual(selected(rows, 'provider_response_completion')[0]['status'], 'INCONCLUSIVE')

    def test_missing_data_acknowledgement_absence_is_unknown_not_fail(self):
        rows = stub(source_status='MISSING_CREDENTIAL', report='Snapshot data unavailable, no verified snapshot was returned.')
        findings = selected(rows, 'missing_source_acknowledgement')
        self.assertEqual(findings[0]['status'], 'PASS')
        rows = stub(source_status='MISSING_CREDENTIAL', report='No comment.')
        self.assertEqual(selected(rows, 'missing_source_acknowledgement')[0]['status'], 'INCONCLUSIVE')

    def test_invalid_candidate_span_is_error_not_false_assertion(self):
        rows = stub(); next(x for x in rows if x['table'] == 'candidates')['quote'] = 'forged'
        with self.assertRaisesRegex(ValueError, 'span binding'):
            r.assess_rows(rows)

    def test_canonical_findings_deterministic_and_no_mutation(self):
        rows = stub(); before = copy.deepcopy(rows)
        self.assertEqual(r.assess_rows(rows), r.assess_rows(list(reversed(rows))))
        self.assertEqual(rows, before)
        self.assertTrue(all(f['finding_id'].startswith('live-finding:') for f in r.assess_rows(rows)))
        limits = selected(rows, 'unresolved_semantic_and_time_limits')[0]
        self.assertEqual(limits['status'], 'INCONCLUSIVE')

    def test_overlapping_candidates_do_not_duplicate_same_number_or_equation(self):
        rows = stub()
        original = next(x for x in rows if x['table'] == 'candidates')
        report = original['quote']; start = report.index('RSI')
        end = report.index('. ', start)+1
        rows.append(dict(original, id='narrow-candidate', start=start, end=end, quote=report[start:end]))
        checks = selected(rows, 'selected_scalar_source_consistency')
        self.assertEqual(sum(f['observed']['field'] == 'rsi' for f in checks), 1)
        self.assertEqual(len(selected(rows, 'selected_subtraction_arithmetic')), 1)
        # A separate malformed surface envelope ending inside the decimal must
        # not become an invented assertion that RSI is 33 instead of 33.07.
        partial_end = report.index('.', start)+1
        rows.append(dict(original, id='partial-number-candidate', start=start, end=partial_end, quote=report[start:partial_end]))
        checks = selected(rows, 'selected_scalar_source_consistency')
        self.assertEqual(sum(f['observed']['field'] == 'rsi' for f in checks), 1)

    def test_discrepancy_acknowledgement_needs_both_versions_preinput(self):
        rows = stub(report='CSV price differs from snapshot close; neither observation is certified final.')
        csv = 'Date,Open,High,Low,Close\n2026-01-01,100,110,90,100\n'
        source = next(x for x in rows if x['table'] == 'sources')
        exposure = next(x for x in rows if x['table'] == 'exposures')
        rows.append(dict(source, id='csv-source', content=csv, sha256=r.text_hash(csv), source_version=r.text_hash(csv), tool='get_stock_data'))
        rows.append(dict(exposure, id='csv-exposure', source_id='csv-source'))
        self.assertEqual(selected(rows, 'source_conflict_acknowledgement')[0]['status'], 'PASS')
        rows[-1]['pre_assertion'] = False
        self.assertEqual(selected(rows, 'source_conflict_acknowledgement'), [])

    def test_clock_context_records_dates_without_ttl_or_stale_verdict(self):
        rows = stub()
        run = next(x for x in rows if x['table'] == 'runs')
        run['context'].update(trade_date='2026-01-02', context_at='2026-01-01T20:00:00Z', context_timezone='UTC')
        f = selected(rows, 'recorded_date_clock_context')[0]
        self.assertEqual(f['status'], 'PASS')
        self.assertEqual(f['observed']['parsed_source_row_dates'], ['2026-01-01'])
        self.assertEqual(f['observed']['freshness_TTL'], 'INCONCLUSIVE')


class AssessmentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.ledger = self.root/'ledger'; self.ledger.mkdir()
        self.rows = stub()
        (self.ledger/'ledger.jsonl').write_text(''.join(r.canonical(x)+'\n' for x in self.rows), encoding='utf-8')
        self.input_hash = hashlib.sha256((self.ledger/'ledger.jsonl').read_bytes()).hexdigest()
        # Isolate persistence contract tests from concurrently developed ingestion.
        import live_verification.ledger as ledger
        self.loader = patch.object(ledger, 'load_ledger', return_value=self.rows)
        self.validator = patch.object(ledger, 'validate_ledger', return_value={'status':'PASS','offline_test_stub':True})
        self.loader.start(); self.addCleanup(self.loader.stop)
        self.validator.start(); self.addCleanup(self.validator.stop)

    def test_build_replay_parity_reproducibility_and_refuse_overwrite(self):
        a, b = self.root/'a', self.root/'b'
        one = r.assess_ledger(self.ledger, a); two = r.assess_ledger(self.ledger, b)
        self.assertEqual(one, two)
        self.assertEqual((a/'findings.jsonl').read_bytes(), (b/'findings.jsonl').read_bytes())
        self.assertEqual(r.validate_assessment(a, self.ledger)['status'], 'PASS')
        self.assertIsNone(one['clearance'])
        with self.assertRaises(FileExistsError): r.assess_ledger(self.ledger, a)
        self.assertEqual(self.input_hash, hashlib.sha256((self.ledger/'ledger.jsonl').read_bytes()).hexdigest())

    def test_rehashed_verdict_with_rebuilt_index_and_summary_rejected_by_replay(self):
        dest = self.root/'assessment'; summary = r.assess_ledger(self.ledger, dest)
        findings = [json.loads(line) for line in (dest/'findings.jsonl').read_text(encoding='utf-8').splitlines()]
        row = next(f for f in findings if f['rule_id'] == 'required_snapshot_invocation')
        row['status'] = 'FAIL'; row.pop('finding_id'); row['finding_id'] = 'live-finding:'+r.digest(row)
        findings.sort(key=lambda x:x['finding_id'])
        raw = ''.join(r.canonical(x)+'\n' for x in findings).encode('utf-8')
        (dest/'findings.jsonl').write_bytes(raw)
        (dest/'findings.sqlite').unlink(); r._write_index(dest/'findings.sqlite', findings)
        forged = r._summary(findings, summary['ledger_sha256'])
        forged.update(findings_sha256=hashlib.sha256(raw).hexdigest(), implementation_binding=summary['implementation_binding'])
        (dest/'summary.json').write_text(r.canonical(forged), encoding='utf-8')
        (dest/'REPORT.md').write_text(r._report(forged, findings), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'replay mismatch'): r.validate_assessment(dest, self.ledger)

    def test_index_scalar_and_implementation_binding_tamper_rejected(self):
        dest = self.root/'assessment'; r.assess_ledger(self.ledger, dest)
        with closing(sqlite3.connect(dest/'findings.sqlite')) as db:
            with db:
                db.execute("UPDATE findings SET status='ERROR' WHERE rowid=1")
        with self.assertRaisesRegex(ValueError, 'parity'): r.validate_assessment(dest)
        summary = json.loads((dest/'summary.json').read_text(encoding='utf-8'))
        summary['implementation_binding']['rules.py'] = '0'*64
        (dest/'summary.json').write_text(r.canonical(summary), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'implementation binding'): r.validate_assessment(dest)

    def test_human_report_tamper_rejected(self):
        dest = self.root/'assessment'; r.assess_ledger(self.ledger, dest)
        (dest/'REPORT.md').write_text('Everything is verified.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'human report'): r.validate_assessment(dest)


if __name__ == '__main__':
    unittest.main()
