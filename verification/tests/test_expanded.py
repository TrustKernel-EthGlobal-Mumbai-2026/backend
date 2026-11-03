"""V2 regression/provenance tests. Never rebuilds historical v1.1 profiles."""
import copy,json,sqlite3,tempfile,unittest
from collections import Counter
from contextlib import closing
from pathlib import Path
from verification import ledger as parent
from verification.corpus import inventory
from verification.expanded import (ROOT,DEST,Expansion,build,load_validate,process_source,rebuild,validate)
from verification.expanded_query import context
from verification.processing import segments,classify,normalize


class ExpandedContracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.before=(ROOT/'verification/data/full/ledger.jsonl').read_bytes()
  cls.coverage=build();cls.rows,cls.manifest=load_validate();cls.by=validate(cls.rows,False)
  cls.base=[r for r in cls.rows if r['table'] in parent.TABLES]

 def changed(self,table,change):
  rows=list(self.rows);i=next(i for i,r in enumerate(rows) if r['table']==table);rows[i]=copy.deepcopy(rows[i]);change(rows[i]);return rows

 def sample(self,text,run='unfamiliar-run-42'):
  source=dict(id=parent.ident('sources_v2',[run,text]),run_id=run,actor='Unfamiliar Analyst',source_type='new_report',asserted_at='2030-02-03T00:00:00Z',text=text)
  e=Expansion();process_source(e,source,[]);return e,source

 def test_historical_parent_and_zip_are_preserved(self):
  self.assertEqual((ROOT/'verification/data/full/ledger.jsonl').read_bytes(),self.before)
  self.assertEqual(parent.sha(self.before),'a55b9624195ab55c908b3d34f31a099117ce77f0f269ed7da609d0c7fcb04912')
  self.assertEqual(parent.sha((ROOT/'verification/data/pilot/ledger.jsonl').read_bytes()),'6d9394f0bbedacf97fd3e899b743c1e3832fbffa1508d618c9cae653b6f7ffb3')
  self.assertEqual(parent.sha((ROOT/'verification/releases/TrustKernel-Atomic-Ledger-Draft-v1.1.zip').read_bytes()),'22054f15033c117f65092c8a76e5a883d0832417296889851ecd724eaedb2dc3')

 def test_inventory_counts_origins_not_copied_state(self):
  self.assertEqual(len(self.by['sources_v2']),60);self.assertEqual(len(self.by['outputs_v2']),78)
  self.assertEqual(len(self.by['appearances_v2']),1744)
  self.assertEqual(sum(len(s['text']) for s in self.by['sources_v2'].values()),195966)
  self.assertEqual(sum(len(s['text']) for s in self.by['sources_v2'].values() if s['report_id']),90269)
  self.assertEqual(set(Counter(s['actor'] for s in self.by['sources_v2'].values()).values()),{6})

 def test_all_chars_partitioned_without_calling_them_verified(self):
  c=self.coverage
  self.assertEqual(sum(c['totals']['disposition_characters'].values()),195966)
  self.assertEqual(c['totals']['unprocessed_characters'],0)
  self.assertEqual(c['totals']['semantically_verified_assertions'],0)
  self.assertIsNone(c['totals']['semantic_recall'])
  self.assertGreater(c['totals']['candidate_kinds']['statement_envelope'],0)

 def test_unfamiliar_run_and_wording_use_same_rules(self):
  e,s=self.sample('Copper inventories are falling. Warehouse deliveries increased.')
  self.assertGreater(len(e.tables['candidates_v2']),0)
  self.assertTrue(all(c['method'].startswith('reusable_surface') for c in e.tables['candidates_v2'].values()))
  self.assertTrue(all(p['source_id']==s['id'] for p in e.tables['passages_v2'].values()))

 def test_conditional_negation_not_forced_into_unconditional_fact(self):
  text='If demand recovers, do not increase exposure unless liquidity improves.'
  e,s=self.sample(text);c=next(iter(e.tables['candidates_v2'].values()));n=e.tables['propositions_v2'][c['proposition_id']]['normalization']
  self.assertEqual(c['quote'],text);self.assertTrue(n['conditions']);self.assertTrue(n['negation'])
  self.assertIsNone(n['subject']);self.assertIsNone(n['value']);self.assertIn('condition_or_coordination_scope',n['unresolved_fields'])
  self.assertEqual(c['candidate_kind'],'statement_envelope')

 def test_compound_and_independent_semicolon_clauses(self):
  e,_=self.sample('Inventories fell and shipments rose.')
  n=next(iter(e.tables['propositions_v2'].values()))['normalization']
  self.assertIn('atomicity',n['unresolved_fields'])
  e,_=self.sample('Inventories fell; Shipments rose.')
  self.assertEqual(len([c for c in e.tables['candidates_v2'].values() if c['parent_candidate_id'] is None]),2)

 def test_background_assertion_not_silently_structural(self):
  e,_=self.sample('## Indicator background\nATR is a volatility measure.\n')
  p=next(p for p in e.tables['passages_v2'].values() if 'ATR is' in p['text'])
  self.assertEqual(p['disposition'],'candidate_assertion')
  self.assertIn('background_context_candidate',p['tags'])

 def test_question_and_unknown_fragment_have_explicit_queue(self):
  e,_=self.sample('Could demand recover?\nUnfamiliar nominal fragments\n')
  self.assertTrue(any(p['disposition']=='question' for p in e.tables['passages_v2'].values()))
  self.assertTrue(any(q['reason']=='unresolved_interpretation' for q in e.tables['queue_v2'].values()))

 def test_unicode_decimal_whitespace_span_roundtrip(self):
  text='  Café inventories are 1.25 units.\n\nIf prices fall, do not buy.  '
  spans=segments(text);self.assertEqual(''.join(text[a:b] for a,b,h in spans),text)
  self.assertFalse(any(text[a:b]=='1.' for a,b,h in spans))
  self.assertEqual(spans[0][0],0);self.assertEqual(spans[-1][1],len(text))

 def test_numeric_child_retains_condition_and_parent(self):
  e,_=self.sample('If the high of $3,100 is exceeded, wait for confirmation.')
  child=next(c for c in e.tables['candidates_v2'].values() if c['candidate_kind']=='explicit_numeric_field_atom')
  self.assertTrue(child['parent_candidate_id'])
  n=e.tables['propositions_v2'][child['proposition_id']]['normalization']
  self.assertTrue(n['conditions']);self.assertEqual(n['value']['text'],'3,100')

 def test_negated_reason_marker_keeps_full_context(self):
  text='Hold is justified not because prices are safe, but because data are missing.'
  e,_=self.sample(text)
  reasons=[r for r in e.tables['relations_v2'].values() if r['relation']=='author_reason_wording']
  self.assertEqual(len(reasons),2)
  self.assertTrue(all(r['quote']==text for r in reasons))
  self.assertTrue(any(r['scope_status'].startswith('negated_reason_marker') for r in reasons))

 def test_unknown_disposition_and_incomplete_output_inventory_rejected(self):
  with self.assertRaisesRegex(ValueError,'Invalid disposition'):
   validate(self.changed('passages_v2',lambda r:r.update(disposition='verified_true')),False)
  removed=next(r['id'] for r in self.rows if r['table']=='outputs_v2')
  with self.assertRaisesRegex(ValueError,'inventory incomplete'):
   validate([r for r in self.rows if r['id']!=removed],False)

 def test_exact_duplicate_text_keeps_distinct_origins(self):
  rows=copy.deepcopy(self.base)
  selected=[r for r in rows if r['table']=='events' and r['kind']=='llm.end' and r['id'] not in {s['output_event_id'] for s in self.by['sources_v2'].values() if s['report_id']} and r['raw']['payload']['response']['generations'][0][0].get('text')][:2]
  for e in selected:e['raw']['payload']['response']['generations'][0][0]['text']='Inventories are lower.'
  sources,_,_=inventory(rows)
  duplicated=[s for s in sources if s['text']=='Inventories are lower.']
  self.assertEqual(len(duplicated),2);self.assertNotEqual(duplicated[0]['id'],duplicated[1]['id']);self.assertEqual(duplicated[0]['content_group'],duplicated[1]['content_group'])

 def test_unhandled_multiple_visible_blocks_is_rejected(self):
  rows=copy.deepcopy(self.base)
  source=next(s for s in self.by['sources_v2'].values() if not s['report_id'])
  event=next(r for r in rows if r['id']==source['output_event_id']);g=event['raw']['payload']['response']['generations'][0][0]
  g['text']='';g['message']['content']=[{'type':'text','text':'First visible text.'},{'type':'text','text':'Second visible text.'}]
  with self.assertRaisesRegex(ValueError,'multi-visible'):inventory(rows)

 def test_source_actor_time_and_normalized_spans_checked(self):
  with self.assertRaisesRegex(ValueError,'actor/time'):
   validate(self.changed('sources_v2',lambda r:r.update(actor='wrong actor')),False)
  rows=self.changed('propositions_v2',lambda r:r['normalization']['numeric_expressions'].append({'text':'invented','start':0,'end':1}))
  with self.assertRaisesRegex(ValueError,'Cue span'):validate(rows,False)

 def test_passage_gap_and_wrong_candidate_quote_rejected(self):
  removed=next(r['id'] for r in self.rows if r['table']=='passages_v2')
  with self.assertRaises(ValueError):validate([r for r in self.rows if r['id']!=removed],False)
  with self.assertRaisesRegex(ValueError,'span mismatch'):
   validate(self.changed('candidates_v2',lambda r:r.update(quote='invented')),False)

 def test_all_stages_have_candidates_and_unmerged_propositions(self):
  sources=self.by['sources_v2'];actors={sources[c['source_id']]['actor'] for c in self.by['candidates_v2'].values()}
  self.assertEqual(len(actors),10)
  self.assertTrue(all(p['identity_status']=='unmerged_source_scoped_candidate' for p in self.by['propositions_v2'].values()))
  self.assertTrue(all(r['status']=='explicit_text_reference_only' for r in self.by['references_v2'].values()))

 def test_context_separates_candidates_from_support(self):
  with closing(sqlite3.connect(DEST/'ledger.sqlite')) as db:
   db.row_factory=sqlite3.Row
   c=next(iter(self.by['candidates_v2'].values()));result=context(db,c['id'])
   self.assertIn(c['quote'],result['enclosing_paragraph']['text'])
   self.assertIn('unresolved_fields',result['candidate']['normalization'])
   self.assertIn('does not establish factual support',result['notice'])

 def test_standalone_index_rebuild_and_stable_build(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'expanded.sqlite';rebuild(self.rows,path)
   with closing(sqlite3.connect(path)) as db:
    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    self.assertEqual(db.execute('SELECT COUNT(*) FROM candidates_v2').fetchone()[0],len(self.by['candidates_v2']))
  self.assertEqual(build()['canonical_sha256'],self.manifest['canonical_sha256'])
  self.assertEqual((ROOT/'verification/data/full/ledger.jsonl').read_bytes(),self.before)


if __name__=='__main__':unittest.main()
