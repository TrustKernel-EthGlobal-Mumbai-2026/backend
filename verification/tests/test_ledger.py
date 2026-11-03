import copy
import json
import sqlite3
import tempfile
import unittest
from collections import Counter
from contextlib import closing
from pathlib import Path

from verification.ledger import (ROOT, SESSION, Ledger, add_report_exposures, build, canonical,
                                decode_envelope, envelope_lineage, ident, rebuild, sha,
                                validate_bundle, validate_index, validate_rows, validate_sources)
from verification.query import assertion_context


class LedgerContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build('pilot')
        build('full')
        cls.rows,cls.manifest = validate_bundle('full')
        cls.by = validate_rows(cls.rows)
        cls.fixture = json.loads((SESSION/'fixture.json').read_text(encoding='utf-8'))

    def changed(self, table, change):
        rows = list(self.rows)
        index = next(i for i,r in enumerate(rows) if r['table']==table)
        rows[index] = copy.deepcopy(rows[index])
        change(rows[index])
        return rows

    def test_all_six_source_chains_and_sqlite_match(self):
        self.assertEqual(len(self.by['events']),1253)
        self.assertEqual(Counter(c['status'] for c in self.by['calls'].values()),{'completed':78,'error':1})
        self.assertEqual(len(self.by['runs']),6)
        self.assertEqual(len({r['fixture_hash'] for r in self.by['runs'].values()}),1)
        self.assertEqual(len({r['config_hash'] for r in self.by['runs'].values()}),1)

    def test_invalid_unicode_span_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'span'):
            validate_rows(self.changed('assertions',lambda r:r.update(start=-1)))
        with self.assertRaisesRegex(ValueError,'span'):
            validate_rows(self.changed('assertions',lambda r:r.update(end=r['end']-1)))

    def test_mismatched_quote_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'span'):
            validate_rows(self.changed('assertions',lambda r:r.update(quote='invented text')))

    def test_orphan_source_reference_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Orphan'):
            validate_rows(self.changed('texts',lambda r:r.update(artifact_id='absent')))

    def test_duplicate_occurrence_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            validate_rows(self.rows+[next(iter(self.by['assertions'].values()))])

    def test_missing_required_values_and_extra_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'required'):
            validate_rows(self.changed('evidence',lambda r:r.update(content=None)))
        with self.assertRaisesRegex(ValueError,'fields'):
            validate_rows(self.changed('assertions',lambda r:r.update(undocumented='x')))

    def test_repeated_occurrences_survive_proposition_sharing(self):
        propositions = [p['id'] for p in self.by['propositions'].values() if p['predicate']=='demand_increase_alleged']
        self.assertEqual(len(propositions),1)
        assertions = [a for a in self.by['assertions'].values() if a['proposition_id']==propositions[0]]
        self.assertEqual(len(assertions),6)
        self.assertEqual(len({a['id'] for a in assertions}),6)
        self.assertEqual(len({a['run_id'] for a in assertions}),6)
        self.assertTrue(all(self.by['propositions'][p]['modality']=='reported_unverified_allegation' for p in propositions))

    def test_declared_duplicate_lineage_does_not_collapse_items(self):
        news = [e for e in self.by['evidence'].values() if e['evidence_key'] in ('E_NEWS','E_GLOBAL')]
        self.assertEqual(len(news),2)
        self.assertEqual(len({e['root_source_id'] for e in news}),1)
        self.assertEqual(len({e['id'] for e in news}),2)
        self.assertEqual(len({e['item_hash'] for e in news}),2)

    def test_no_data_is_not_positive_market_evidence(self):
        missing = {e['evidence_key'] for e in self.by['evidence'].values() if e['content_status']=='NO_DATA'}
        self.assertEqual(missing,{'E_MACRO','E_PREDICTION','E_INDICATOR'})
        self.assertEqual(next(e['content_status'] for e in self.by['evidence'].values() if e['evidence_key']=='E_SNAPSHOT'),'PARTIAL')
        self.assertTrue(all(l['status']=='extractor-proposed' for l in self.by['links'].values() if l['relation']=='support_candidate'))

    def test_csv_delivery_decodes_nested_json_newlines(self):
        csv_id = next(e['id'] for e in self.by['evidence'].values() if e['evidence_key']=='E_PRICE')
        exposures = [e for e in self.by['exposures'].values() if e['evidence_id']==csv_id and e['mode']=='decoded_tool_result_lineage']
        self.assertEqual(len(exposures),6)
        for exposure in exposures:
            text = self.by['texts'][exposure['text_id']]
            self.assertEqual(text['transform'],'json_parse:/evidence/content')
            self.assertIn('\nDate,Open,High',text['text'])

    def test_available_snapshot_does_not_imply_retrieved_or_delivered(self):
        snapshot = next(e['id'] for e in self.by['evidence'].values() if e['evidence_key']=='E_SNAPSHOT')
        self.assertEqual(sum(a['evidence_id']==snapshot for a in self.by['availability'].values()),6)
        self.assertEqual(sum(a['evidence_id']==snapshot for a in self.by['retrievals'].values()),3)
        for exposure in self.by['exposures'].values():
            if exposure['evidence_id']==snapshot:
                self.assertTrue(self.by['calls'][exposure['call_id']]['run_id'].startswith('terra-'))

    def test_missing_exposure_inventory_is_rejected(self):
        call_ids = {a['call_id'] for a in self.by['assertions'].values()}
        exposure = next(e for e in self.by['exposures'].values() if e['call_id'] in call_ids)
        rows = [r for r in self.rows if r['id']!=exposure['id']]
        with self.assertRaisesRegex(ValueError,'exposure inventory'):
            validate_rows(rows)

    def test_exposure_from_another_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'model input|exposure inventory'):
            validate_rows(self.changed('exposures',lambda r:r.update(call_id=next(c['id'] for c in self.by['calls'].values() if c['id']!=r['call_id']))))

    def test_uri_citations_survive_without_literal_ids(self):
        news = next(r for r in self.by['reports'].values() if r['run_id']=='terra-f381dc458057' and r['field']=='news_report')
        mentions = [m for m in self.by['mentions'].values() if m['report_id']==news['id']]
        self.assertTrue(any(m['form']=='uri' for m in mentions))
        self.assertFalse(any(m['form']=='literal_id' for m in mentions))

    def test_protocol_failure_and_conditional_numerical_match_coexist(self):
        failed = {c['subject_id'] for c in self.by['checks'].values() if c['category']=='required_tool_compliance' and c['result']=='FAIL'}
        self.assertEqual(len(failed),3)
        matches = [c for c in self.by['checks'].values() if c['category']=='conditional_fixture_comparison' and c['result']=='MATCH'
                   and self.by['assertions'][c['subject_id']]['report_id'] in failed]
        self.assertGreater(len(matches),0)
        self.assertTrue(all(c['details']['recorded_csv_exposure_ids'] for c in matches))

    def envelope_case(self):
        raw = next(e['raw'] for e in self.by['events'].values() if e['kind']=='evidence.retrieved' and e['raw']['payload']['evidence']['evidence_id']=='E_PRICE')
        envelope = copy.deepcopy(raw['payload'])
        content = json.dumps(envelope,ensure_ascii=False)
        start = dict(run_id='test-run',seq=4)
        message = dict(type='tool',tool_call_id='test-call',content=content)
        events = [dict(run_id='test-run',seq=1,kind='evidence.retrieved',payload=envelope),
                  dict(run_id='test-run',seq=2,kind='tool.end',payload={'output':{'content':content,'tool_call_id':'test-call'}})]
        ids = {1:'retrieval-1',2:'result-2'}
        decoded = decode_envelope(content,list(self.by['evidence'].values()),self.fixture)
        return envelope,content,start,message,events,ids,decoded

    def test_malformed_envelope_is_rejected(self):
        decoded = decode_envelope('{"evidence":',list(self.by['evidence'].values()),self.fixture)
        self.assertEqual(decoded['reason'],'malformed_json')

    def test_self_declared_hash_and_spoofed_source_are_not_authority(self):
        envelope,*_ = self.envelope_case()
        envelope['content_hash'] = 'invented'
        self.assertEqual(decode_envelope(json.dumps(envelope),list(self.by['evidence'].values()),self.fixture)['reason'],'declared_hash_mismatch')
        envelope,*_ = self.envelope_case()
        envelope['provenance']['provider'] = 'spoofed publisher'
        self.assertEqual(decode_envelope(json.dumps(envelope),list(self.by['evidence'].values()),self.fixture)['reason'],'fixture_wrapper_mismatch')

    def test_partial_or_changed_evidence_is_not_full_content_delivery(self):
        envelope,*_ = self.envelope_case()
        envelope['evidence']['content'] = envelope['evidence']['content'][:40]
        self.assertEqual(decode_envelope(json.dumps(envelope),list(self.by['evidence'].values()),self.fixture)['reason'],'item_mismatch')

    def test_repeated_id_only_is_not_envelope_or_evidence_content(self):
        text = 'E_PRICE E_PRICE fixture://eth-synthetic-v1'
        self.assertIsNone(decode_envelope(text,list(self.by['evidence'].values()),self.fixture))
        evidence = next(e for e in self.by['evidence'].values() if e['evidence_key']=='E_PRICE')
        self.assertNotIn(evidence['content'],text)

    def test_valid_envelope_in_human_or_assistant_prose_is_presence_only(self):
        _,content,start,message,events,ids,decoded = self.envelope_case()
        for role in ('human','ai'):
            message.update(type=role)
            mode,provenance = envelope_lineage(decoded,message,start,events,ids)
            self.assertEqual(mode,'decoded_envelope_presence')
            self.assertEqual(provenance['verified_tool_result_ids'],[])
            self.assertEqual(provenance['matching_prior_tool_result_ids'],['result-2'])
        self.assertIsNone(decode_envelope('Quoted payload: '+content,list(self.by['evidence'].values()),self.fixture))

    def test_legitimate_wrapup_preserves_content_without_invented_tool_role(self):
        _,content,start,message,events,ids,_ = self.envelope_case()
        message.update(type='human',tool_call_id=None,content='[get_stock_data returned]\n'+content)
        decoded = decode_envelope(message['content'],list(self.by['evidence'].values()),self.fixture)
        mode,provenance = envelope_lineage(decoded,message,start,events,ids)
        self.assertEqual(mode,'decoded_envelope_presence')
        self.assertEqual(decoded['transform'],'tool_return_prefix_then_json_parse:/evidence/content')
        self.assertEqual(provenance['matching_prior_tool_result_ids'],['result-2'])
        self.assertEqual(provenance['verified_tool_result_ids'],[])
        self.assertEqual(decode_envelope('[get_news returned]\n'+content,list(self.by['evidence'].values()),self.fixture)['reason'],'wrapper_tool_mismatch')

    def test_tool_lineage_requires_correct_call_id_run_and_time(self):
        _,_,start,message,events,ids,decoded = self.envelope_case()
        self.assertEqual(envelope_lineage(decoded,message,start,events,ids)[0],'decoded_tool_result_lineage')
        message['tool_call_id'] = 'another-call'
        self.assertEqual(envelope_lineage(decoded,message,start,events,ids)[0],'decoded_envelope_presence')
        message['tool_call_id'] = 'test-call'
        for event in events:
            event['run_id'] = 'another-run'
        self.assertEqual(envelope_lineage(decoded,message,start,events,ids)[1]['matching_prior_tool_result_ids'],[])
        for event in events:
            event['run_id'] = 'test-run'
        start['seq'] = 1
        self.assertEqual(envelope_lineage(decoded,message,start,events,ids)[1]['matching_prior_tool_result_ids'],[])

    def test_repeated_report_embedding_retains_occurrences(self):
        # Reuse a real recorded input/report relation, then put two copies in that
        # input. The derived occurrences must survive instead of deduplicating.
        exposure = next(e for e in self.by['exposures'].values() if e['mode']=='exact_prior_report')
        ledger = Ledger()
        for table in ('calls','events','texts','reports'):
            ledger.rows[table] = copy.deepcopy(self.by[table])
        input_text = ledger.rows['texts'][exposure['text_id']]
        quote = exposure['quote']
        input_text['text'] = quote+'\n\n'+quote
        add_report_exposures(ledger)
        occurrences = [e for e in ledger.rows['exposures'].values() if e['text_id']==input_text['id'] and e['report_id']==exposure['report_id']]
        self.assertEqual(len(occurrences),2)
        self.assertNotEqual(occurrences[0]['id'],occurrences[1]['id'])

    def test_report_context_cannot_cross_runs_or_precede_output(self):
        exposure = next(e for e in self.by['exposures'].values() if e['mode']=='exact_prior_report')
        report = self.by['reports'][exposure['report_id']]
        rows = list(self.rows)
        index = next(i for i,r in enumerate(rows) if r['id']==report['id'])
        rows[index] = dict(rows[index],run_id='different-run')
        with self.assertRaises(ValueError):
            validate_rows(rows)
        # Missing output identity also fails before a report can be treated as visible.
        rows[index] = dict(rows[index],output_event_id='not-an-event')
        with self.assertRaises(ValueError):
            validate_rows(rows)

    def test_every_saved_report_has_exact_origin_but_partial_atomization(self):
        self.assertEqual(len(self.by['reports']),30)
        self.assertFalse(any(r['origin_method']=='unresolved' for r in self.by['reports'].values()))
        atomized = {a['report_id'] for a in self.by['assertions'].values()}
        self.assertEqual(len(atomized),18)
        self.assertTrue(all(r['id'] not in atomized for r in self.by['reports'].values() if r['field'] in ('investment_plan','trader_investment_plan')))

    def test_raw_event_tampering_is_rejected(self):
        rows = self.changed('events',lambda r:r['raw']['payload'].update(invented=True))
        with self.assertRaisesRegex(ValueError,'event hash'):
            validate_rows(rows)

    def test_source_file_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'source.json'
            path.write_text('{"text":"original"}',encoding='utf-8')
            ledger = Ledger(root)
            aid = ledger.artifact(path)
            ledger.text(aid,'/text','original')
            validate_sources(ledger.all(),root)
            path.write_text('{"text":"changed"}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'changed'):
                validate_sources(ledger.all(),root)

    def test_sqlite_is_rebuildable_without_raw_source_access(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'rebuilt.sqlite'
            rebuild(self.rows,path)
            validate_index(self.rows,path)
            with closing(sqlite3.connect(path)) as db,db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM assertion_details').fetchone()[0],86)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                db.execute("UPDATE assertions SET quote='altered index'")
            with self.assertRaisesRegex(ValueError,'Index rows differ'):
                validate_index(self.rows,path)

    def test_repeat_build_has_stable_ids_and_content_hash(self):
        previous = self.manifest['canonical_sha256']
        summary = build('full')
        self.assertEqual(previous,summary['canonical_sha256'])
        self.assertEqual(self.manifest['build_id'],summary['build_id'])
        self.assertEqual(ident('example',{'a':1,'b':2}),ident('example',{'b':2,'a':1}))

    def test_context_query_keeps_paragraph_mapping_checks_and_input_separate(self):
        with closing(sqlite3.connect((ROOT/'verification/data/full/ledger.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
            db.row_factory = sqlite3.Row
            assertion = next(a for a in self.by['assertions'].values() if self.by['propositions'][a['proposition_id']]['predicate']=='close')
            context = assertion_context(db,assertion['id'],True)
            self.assertIn(assertion['quote'],context['paragraph']['text'])
            self.assertIn('assumptions',context['candidate_proposition'])
            self.assertEqual(context['candidate_proposition']['identity_status'],'candidate_equivalence_awaiting_adjudication')
            self.assertEqual(context['recorded_input_event']['kind'],'llm.start')
            self.assertTrue(any(c['category']=='conditional_fixture_comparison' for c in context['checks']))
            with self.assertRaisesRegex(ValueError,'Unknown assertion'):
                assertion_context(db,'obsolete-build-id')


if __name__=='__main__':
    unittest.main()
