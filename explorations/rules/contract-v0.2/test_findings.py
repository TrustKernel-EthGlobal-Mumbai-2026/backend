"""Run this file directly; never discovers or imports historical ledger tests."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import finding_packets as f


class MechanismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=f.Ledger()
        cls.mapping=json.loads((f.LANE/'mappings.json').read_text(encoding='utf-8'))['mappings'][0]

    @classmethod
    def tearDownClass(cls):
        cls.ledger.assert_unchanged()
        cls.ledger.close()

    def test_real_scalar_and_incomplete_companion(self):
        good=f.scalar_case(self.ledger,self.mapping,'2026-11-01T14:37:31Z')
        self.assertEqual(good['result']['status'],'PASS')
        self.assertEqual(good['observed']['value'],'2540')
        self.assertFalse(good['accepted_factual_support'])
        missing=copy.deepcopy(self.mapping);missing['unit']=None
        result=f.scalar_case(self.ledger,missing,'2026-11-01T14:37:31Z')
        self.assertEqual(result['result']['status'],'INCONCLUSIVE')

    def test_entity_date_unit_scope_are_prerequisites(self):
        for key,value in [('entity','BTC-USD'),('valid_date','2026-10-29'),('unit','EUR'),('scope','live_market')]:
            with self.subTest(key=key):
                mapping=copy.deepcopy(self.mapping);mapping[key]=value
                result=f.scalar_case(self.ledger,mapping,'2026-11-01T14:37:31Z')
                self.assertEqual(result['result']['status'],'INCONCLUSIVE')

    def test_rejected_mapping_status_and_bad_value_do_not_pass(self):
        mapping=copy.deepcopy(self.mapping);mapping['status']='withdrawn'
        self.assertEqual(f.scalar_case(self.ledger,mapping,'2026-11-01T14:37:31Z')['result']['status'],'INCONCLUSIVE')
        mapping=copy.deepcopy(self.mapping);mapping['value']='NaN'
        self.assertEqual(f.scalar_case(self.ledger,mapping,'2026-11-01T14:37:31Z')['result']['status'],'ERROR')

    def test_bad_authored_context_gate_is_not_false_fact(self):
        mapping=copy.deepcopy(self.mapping);mapping['context_quotes']=['An absent authored mapping context']
        self.assertEqual(f.scalar_case(self.ledger,mapping,'2026-11-01T14:37:31Z')['result']['status'],'INCONCLUSIVE')

    def test_exact_arithmetic_mismatch_is_scoped_failure(self):
        met=[f.prereq('tuple',True,'test-only declared tuple')]
        self.assertEqual(f.compare_scalar('2,540','2541',met)[:2],('FAIL','SCALAR_MISMATCH_UNDER_MAPPING'))
        unknown=[f.prereq('unit',False,'omitted')]
        self.assertEqual(f.compare_scalar('2540','2541',unknown)[0],'INCONCLUSIVE')

    def test_invalid_numbers_are_errors_not_factual_failures(self):
        for text in ['NaN','Infinity','2,54','2_540','1e3','',None,True]:
            with self.subTest(text=text):
                self.assertEqual(f.compare_scalar(text,'2540',[])[0],'ERROR')

    def test_stale_ids_and_path_traversal_fail_closed(self):
        with self.assertRaisesRegex(f.BindingError,'UNKNOWN_OR_STALE'):
            self.ledger.row('clauses_v3:rejected-stale-id')
        with self.assertRaisesRegex(f.BindingError,'OUTSIDE_ROOT'):
            self.ledger.path('../outside.json')

    def test_bad_span_cannot_be_reproduced(self):
        a=self.ledger.select('assertions',**self.mapping['selector'])
        report=self.ledger.row(a['report_id'])
        with self.assertRaisesRegex(f.BindingError,'SPAN_MISMATCH'):
            self.ledger.anchor(report['text_id'],a['start']+1,a['end'],a['quote'])

    def test_decoded_csv_is_real_input_scope(self):
        a=self.ledger.select('assertions',**self.mapping['selector'])
        evidence,_,_=self.ledger.evidence('E_PRICE')
        exposures=self.ledger.exposure_witnesses(a['call_id'],evidence['id'])
        self.assertTrue(exposures)
        self.assertTrue(any('json_parse' in (x['anchor']['transform'] or '') for x in exposures))
        final=self.ledger.select('sources_v2',run_id='terra-2f66dbe7f15d',source_type='final_trade_decision')
        self.assertEqual(self.ledger.exposure_witnesses(final['call_id'],evidence['id']),[])

    def test_missing_prerequisite_cannot_have_definite_envelope(self):
        subject=self.ledger.subject(self.ledger.select('assertions',**self.mapping['selector']))
        with self.assertRaisesRegex(f.BindingError,'UNMET_PREREQUISITES'):
            f.envelope(self.ledger,'test','numeric','test',subject,{}, {'corpus':'test'},
                [f.prereq('unit',False,'omitted')],None,None,'FAIL','bad','2026-11-01T14:37:31Z')

    def test_readonly_source_connection_and_disposable_write_rejection(self):
        self.assertEqual(self.ledger.conn.execute('PRAGMA query_only').fetchone()[0],1)
        work=f.LANE/'work';work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            path=Path(temp)/'copy.sqlite'
            c=sqlite3.connect(path)
            try:
                c.execute('CREATE TABLE example (value TEXT)')
                c.execute("INSERT INTO example VALUES ('unchanged')")
                c.commit()
            finally:c.close()
            c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    c.execute("UPDATE example SET value='changed'")
            finally:c.close()

    def test_pin_mutation_is_rejected_before_binding(self):
        work=f.LANE/'work';work.mkdir(exist_ok=True)
        pin=copy.deepcopy(self.ledger.pin);pin['canonical_sha256']='0'*64
        with tempfile.TemporaryDirectory(dir=work) as temp:
            path=Path(temp)/'pin.json';path.write_text(json.dumps(pin),encoding='utf-8')
            with self.assertRaisesRegex(f.BindingError,'UNAPPROVED_RELEASE_PIN'):
                f.Ledger(pin_path=path)

    def test_pinned_artifact_digest_mutation_is_rejected(self):
        work=f.LANE/'work';work.mkdir(exist_ok=True)
        pin=copy.deepcopy(self.ledger.pin);pin['artifacts'][0]['sha256']='0'*64
        with tempfile.TemporaryDirectory(dir=work) as temp:
            path=Path(temp)/'pin.json';path.write_text(json.dumps(pin),encoding='utf-8')
            with self.assertRaisesRegex(f.BindingError,'PINNED_ARTIFACT_HASH_MISMATCH'):
                f.Ledger(pin_path=path)

    def test_sqlite_selected_row_mismatch_is_rejected(self):
        probe=object.__new__(f.Ledger)
        probe.rows={'example:local':{'id':'example:local','table':'example','quote':'expected'}}
        probe.checked_rows=set()
        probe.conn=sqlite3.connect(':memory:');probe.conn.row_factory=sqlite3.Row
        try:
            probe.conn.execute('CREATE TABLE example (id TEXT, quote TEXT)')
            probe.conn.execute('INSERT INTO example VALUES (?,?)',('example:local','different'))
            with self.assertRaisesRegex(f.BindingError,'SQLITE_ROW_MISMATCH'):
                probe.row('example:local')
        finally:probe.close()

    def test_changed_bytes_refused_and_identical_bytes_idempotent(self):
        work=f.LANE/'work';work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            path=Path(temp)/'finding.json'
            f.write_once(path,b'original');f.write_once(path,b'original')
            with self.assertRaisesRegex(f.BindingError,'REFUSE_CHANGED_BYTE_OVERWRITE'):
                f.write_once(path,b'mutated')

    def test_identity_binds_mapping_and_assessment_time(self):
        first=f.scalar_case(self.ledger,self.mapping,'2026-11-01T14:37:31Z')
        same=f.scalar_case(self.ledger,self.mapping,'2026-11-01T14:37:31Z')
        later=f.scalar_case(self.ledger,self.mapping,'2026-11-01T14:37:32Z')
        self.assertEqual(f.canonical(first),f.canonical(same))
        self.assertNotEqual(first['finding_id'],later['finding_id'])
        mapping=copy.deepcopy(self.mapping);mapping['version']='0.2.1-test'
        changed=f.scalar_case(self.ledger,mapping,'2026-11-01T14:37:31Z')
        self.assertNotEqual(first['check']['check_id'],changed['check']['check_id'])

    def test_root_equality_does_not_make_unknown_or_different_roots_independent(self):
        self.assertEqual(f.root_relation('root-a','root-a')[:2],('PASS','DECLARED_ROOT_SHARED'))
        self.assertEqual(f.root_relation('root-a','root-b')[0],'INCONCLUSIVE')
        self.assertEqual(f.root_relation(None,None)[0],'INCONCLUSIVE')
        self.assertEqual(f.root_relation('','')[0],'INCONCLUSIVE')

    def test_r035_real_source_and_cross_branch_mutation(self):
        registry=json.loads((f.LANE/'case-registry.json').read_text(encoding='utf-8'))['cases']['semicolon_regression']
        early=self.ledger.row(registry['earlier_clause_id']);later=self.ledger.row(registry['later_clause_id'])
        first=self.ledger.row(early['proposition_id'])['normalization'];second=self.ledger.row(later['proposition_id'])['normalization']
        source=self.ledger.row(early['source_id'])
        self.assertTrue(f.condition_bounds(source['text'],early,first))
        self.assertTrue(f.condition_bounds(source['text'],later,second))
        self.assertEqual(first['condition_spans'],[])
        self.assertEqual(second['condition_spans'][0]['text'],'uninvested')
        mutated=copy.deepcopy(first);mutated['condition_spans']=copy.deepcopy(second['condition_spans'])
        with self.assertRaisesRegex(f.BindingError,'CONDITION_OUTSIDE_LOCAL_BRANCH'):
            f.condition_bounds(source['text'],early,mutated)
        mutated=copy.deepcopy(first);mutated['scope']['attachment_end']=first['scope']['frame_end']
        with self.assertRaisesRegex(f.BindingError,'CONTAINS_SEMICOLON'):
            f.condition_bounds(source['text'],early,mutated)

    def test_rejected_reason_cannot_be_endorsed_or_move_to_another_frame(self):
        registry=json.loads((f.LANE/'case-registry.json').read_text(encoding='utf-8'))['cases']['reason_roles']
        pos=self.ledger.row(registry['positive_clause_id']);neg=self.ledger.row(registry['rejected_clause_id'])
        pn=self.ledger.row(pos['proposition_id'])['normalization'];nn=self.ledger.row(neg['proposition_id'])['normalization']
        text=self.ledger.row(pos['source_id'])['text']
        result=f.rationale_roles(text,pos,pn,neg,nn)
        self.assertFalse(result['rejected_reason_promoted_to_support'])
        mutated=copy.deepcopy(neg);mutated['role']='declared_reason'
        with self.assertRaisesRegex(f.BindingError,'ROLE_MARKER_MISMATCH'):
            f.rationale_roles(text,pos,pn,mutated,nn)
        mutated=copy.deepcopy(neg);mutated['frame_id']='wrong-frame'
        with self.assertRaisesRegex(f.BindingError,'NOT_SAME_FRAME'):
            f.rationale_roles(text,pos,pn,mutated,nn)

    def test_case_set_is_bounded_and_missing_policy_is_explicit(self):
        registry=json.loads((f.LANE/'case-registry.json').read_text(encoding='utf-8'))
        findings=f.extra_cases(self.ledger,'2026-11-01T14:37:31Z',registry)
        cases={x['case_id']:x for x in findings}
        self.assertEqual(len(cases),10)
        self.assertEqual(cases['PROTOCOL-SOL-SNAPSHOT']['result']['status'],'FAIL')
        self.assertEqual(cases['PRICE-SOL-RELATION']['result']['status'],'PASS')
        self.assertTrue(cases['PRICE-SOL-RELATION']['observed']['recorded_input_exposures'])
        self.assertEqual(cases['PREDICTION-SCALAR-APPLICABILITY']['result']['status'],'NOT_APPLICABLE')
        self.assertIsNone(cases['PREDICTION-SCALAR-APPLICABILITY']['observed']['probability'])
        self.assertEqual(cases['HOLD-CONDITIONAL-APPLICABILITY']['result']['status'],'INCONCLUSIVE')
        self.assertEqual(cases['RATIONALE-SUFFICIENCY']['result']['status'],'INCONCLUSIVE')
        self.assertIn('namespace',cases['PROTOCOL-SOL-SNAPSHOT']['subject']['occurrence'])
        self.assertTrue(all(not x['accepted_factual_support'] for x in findings))

    def test_explicit_supersedes_keeps_prior_finding_intact(self):
        prior=f.scalar_case(self.ledger,self.mapping,'2026-11-01T14:37:31Z')
        serialized=f.canonical(prior)
        later=f.envelope(self.ledger,prior['case_id'],prior['check']['type'],prior['check']['method_version'],
            prior['subject'],prior['mapping'],prior['ledger_context']['context'],prior['required_prerequisites'],
            prior['expected'],prior['observed'],'PASS','SCALAR_EQUAL_UNDER_MAPPING','2026-11-01T14:37:32Z',
            prior['positive_witnesses'],prior['negative_witnesses'],prior['assumptions'],supersedes=prior['finding_id'])
        self.assertEqual(later['supersedes'],prior['finding_id'])
        self.assertNotEqual(later['finding_id'],prior['finding_id'])
        self.assertEqual(f.canonical(prior),serialized)

    def test_schema_required_fields_and_digests_match_real_envelopes(self):
        schema=json.loads((f.LANE/'finding-envelope.schema.json').read_text(encoding='utf-8'))
        registry=json.loads((f.LANE/'case-registry.json').read_text(encoding='utf-8'))
        findings=[f.scalar_case(self.ledger,self.mapping,'2026-11-01T14:37:31Z')]+f.extra_cases(self.ledger,'2026-11-01T14:37:31Z',registry)
        for finding in findings:
            self.assertEqual(set(finding),set(schema['required']))
            value=dict(finding);saved=value.pop('finding_id')
            self.assertEqual(saved,'finding:'+f.digest(value))
            self.assertIn(finding['result']['status'],f.STATUSES)
            self.assertFalse(finding['accepted_factual_support'])
            a=finding['subject']['anchor']
            self.assertLess(a['start'],a['end'])

    def test_absent_anchored_case_fails_instead_of_fabricating_source(self):
        source=self.ledger.select('sources_v2',run_id='sol-0530a9827c2c',source_type='market_report')
        with self.assertRaisesRegex(f.BindingError,'AUTHORED_SPAN_NOT_UNIQUE'):
            self.ledger.authored_span_subject(source,'This sentence is absent from the source.','test')


if __name__=='__main__':
    unittest.main()
