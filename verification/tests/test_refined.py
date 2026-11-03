"""Declared-rule/provenance regressions; not independent semantic evaluation."""
import copy,json,re,sqlite3,tempfile,unittest
from pathlib import Path
from contextlib import closing
from verification import ledger as base,refine_rules as rules
from verification.refined import ROOT,DEST,build,load_validate,validate,validate_index,rebuild,group,runtime
from verification.refined_query import clause_context


class RefinementContracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.coverage=build();cls.rows,cls.manifest=load_validate();cls.by=group(cls.rows)

 def change(self,table,fn):
  rows=list(self.rows);i=next(i for i,r in enumerate(rows) if r['table']==table);rows[i]=copy.deepcopy(rows[i]);fn(rows[i]);return rows

 def parsed(self,text):
  children=rules.decompose(text,0,len(text))
  return children,[rules.normalization(text,c,0,len(text),0,len(text)) for c in children]

 def test_all_priority_sources_and_historical_releases_preserved(self):
  primary=[s for s in self.by['scope_v3'].values() if s['priority']]
  self.assertEqual(len(primary),18)
  self.assertEqual(base.sha((ROOT/'verification/data/expanded-v2/ledger.jsonl').read_bytes()),'401d716ff7cb007d2a44c8d23177b04f490983b0371b1507340b1a281686dd35')
  self.assertEqual(base.sha((ROOT/'verification/data/full/ledger.jsonl').read_bytes()),'a55b9624195ab55c908b3d34f31a099117ce77f0f269ed7da609d0c7fcb04912')
  self.assertEqual(base.sha((ROOT/'verification/data/pilot/ledger.jsonl').read_bytes()),'6d9394f0bbedacf97fd3e899b743c1e3832fbffa1508d618c9cae653b6f7ffb3')
  self.assertEqual(base.sha((ROOT/'verification/releases/TrustKernel-Expanded-Candidate-Ledger-v2.zip').read_bytes()),'2a4dd9267b999569d582ad948a7db0466f011ef822d2a822fde6842930f9e413')

 def test_section_label_is_metadata_not_semantic_predicate(self):
  text='**Investment Thesis**: Copper demand is uncertain.'
  frames=rules.frames(text);self.assertEqual(frames[0][2],'section_metadata')
  a,b,k,s=next(f for f in frames if f[2]=='sentence_frame')
  n=rules.normalization(text,rules.decompose(text,a,b)[0],a,b,0,len(text))
  self.assertEqual(n['predicate']['text'],'is');self.assertEqual(n['subject']['text'],'Copper demand')
  self.assertNotIn('Investment Thesis',n['predicate']['text'])

 def test_known_discourse_false_atom_abstains(self):
  text='Let me separate the structural opportunity from what this unusually limited dataset actually shows.'
  c,n=self.parsed(text);self.assertEqual(n[0]['kind'],'discourse');self.assertIsNone(n[0]['predicate']);self.assertIsNone(n[0]['value'])
  actual=[p for p in self.by['clauses_v3'].values() if p['quote']==text]
  self.assertTrue(actual);self.assertTrue(all(p['kind']=='discourse' for p in actual))

 def test_no_punctuation_only_normalized_values(self):
  for p in self.by['propositions_v3'].values():
   value=p['normalization']['value']
   self.assertTrue(value is None or re.search(r'\w',value['text']))

 def test_scalar_hold_is_declaration_not_imperative(self):
  scalars=[c for c in self.by['clauses_v3'].values() if c['kind']=='scalar_report_declaration' and c['quote']=='Hold']
  self.assertTrue(scalars)
  for c in scalars:
   n=self.by['propositions_v3'][c['proposition_id']]['normalization']
   self.assertIsNone(n['subject']);self.assertIsNone(n['predicate']);self.assertEqual(n['value']['text'],'Hold')

 def test_positive_and_negated_reasons_are_distinct(self):
  text='Hold wins because evidence is sparse—not because analysts disagree.'
  c,n=self.parsed(text)
  self.assertEqual([p['role'] for p in c],['reason_conclusion','declared_reason','rejected_reason'])
  self.assertEqual(text[c[1]['start']:c[1]['end']],'evidence is sparse')
  self.assertEqual(n[2]['inherited_frame_cues']['negation'][0]['text'],'not')
  self.assertTrue(all(p['accepted_factual_support'] is False for p in n))

 def test_not_only_because_abstains_on_reason_polarity(self):
  c,n=self.parsed('We hold not only because demand is uncertain.')
  self.assertTrue(any(p['role']=='reason_polarity_unresolved' for p in c))

 def test_compound_reason_remains_explicitly_unresolved(self):
  c,n=self.parsed('We hold because prices are uncertain and supply is missing.')
  reason=next(x for x in n if x['role']=='declared_reason')
  self.assertIn('within_component_coordination_unresolved',reason['unresolved'])
  self.assertEqual(reason['kind'],'author_rationale_component');self.assertFalse(reason['accepted_factual_support'])

 def test_noun_list_after_attribution_colon_not_split(self):
  c,n=self.parsed('The analyst rejects a reversal: rising highs and lows coexist with a weaker close.')
  self.assertEqual(len(c),1);self.assertIn('coordination_or_shared_scope_unresolved',n[0]['unresolved'])

 def test_simple_independent_clauses_keep_coordination(self):
  c,n=self.parsed('Copper demand is weak and warehouse supply is high.')
  self.assertEqual(len(c),2);self.assertTrue(all(x['connector'] for x in c))
  self.assertTrue(all('coordination_semantics_not_inferred' in x['unresolved'] for x in n))

 def test_nested_conditions_never_become_unconditional(self):
  text='If invested, maintain exposure only if liquidity is sufficient.'
  c,n=self.parsed(text)
  self.assertEqual({x['role'] for x in c},{'condition_antecedent','conditional_outcome'})
  for value in n:
   self.assertEqual(len(value['inherited_frame_cues']['conditions']),2)
   self.assertIn('nested_condition_boolean_scope_unresolved',value['unresolved'])
   self.assertEqual(value['kind'],'conditional_component')

 def test_alternative_condition_scope_preserved(self):
  text='Reduce exposure if volatility rises or if liquidity disappears.'
  c,n=self.parsed(text)
  self.assertEqual(len(c),1);self.assertEqual(c[0]['role'],'conditional_envelope')
  self.assertIn('alternative_condition_markers_preserved',n[0]['unresolved'])

 def test_real_contextual_semicolon_if_does_not_govern_prior_advice(self):
  text='For this frozen synthetic fixture, maintain existing ETH exposure provisionally within established portfolio limits; if uninvested, do not initiate, and make no additions, thesis-driven trims, or leverage increases.'
  c,n=self.parsed(text);boundary=text.index(';')
  prior=[x for x in c if x['end']<=boundary]
  self.assertEqual(len(prior),1);self.assertEqual(prior[0]['condition_spans'],[])
  self.assertNotEqual(prior[0]['role'],'conditional_outcome')
  self.assertTrue(any(x['role']=='condition_antecedent' and text[x['start']:x['end']]=='uninvested' for x in c))
  outcome=next(x for x in c if x['role']=='conditional_outcome')
  self.assertGreater(outcome['start'],boundary)
  self.assertEqual(outcome['condition_spans'][0]['text'],'uninvested')
  self.assertTrue(any('other_branch_condition_context_unassigned' in x['unresolved'] for x in n if x['scope']['attachment_end']<=boundary))
  # This must also hold in the actual source/frame stored in the generated packet corpus.
  frame=next(f for f in self.by['frames_v3'].values() if f['quote']==text)
  for clause in self.by['clauses_v3'].values():
   if clause['frame_id']==frame['id'] and clause['end']<=frame['start']+boundary:
    self.assertEqual(self.by['propositions_v3'][clause['proposition_id']]['normalization']['condition_spans'],[])

 def test_unfamiliar_contextual_comma_list_variants_keep_if_local(self):
  variants=[
   'During the warehouse review, preserve copper reserves, monitoring transport costs; if liquidity disappears, do not add leverage.',
   'For this paper-only exercise, retain inventory within storage limits; when cash is scarce, avoid new purchases.',
   'Across this provisional scenario, monitor costs, fees and supply; if unallocated, remain flat.'
  ]
  for text in variants:
   with self.subTest(text=text):
    c,n=self.parsed(text);boundary=text.index(';')
    self.assertTrue(all(not x['condition_spans'] for x in c if x['end']<=boundary))
    self.assertTrue(any(x['role']=='conditional_outcome' and x['start']>boundary for x in c))

 def test_ordinary_independent_semicolon_if_keeps_local_guard(self):
  text='Maintain reserves; if volatility rises, reduce exposure.'
  c,n=self.parsed(text);prior=c[0]
  self.assertEqual(text[prior['start']:prior['end']],'Maintain reserves')
  self.assertEqual(prior['condition_spans'],[])
  outcome=next(x for x in c if x['role']=='conditional_outcome')
  self.assertEqual(outcome['condition_spans'][0]['text'],'volatility rises')
  self.assertEqual(text[outcome['start']:outcome['end']],'reduce exposure.')
  self.assertTrue(all(x.get('boundary_rule')=='R035' for x in c))

 def test_reason_and_prefix_scope_do_not_consume_later_semicolon_branch(self):
  text='We hold because data are missing; if no position is held, do not initiate.'
  c,n=self.parsed(text)
  reason=next(x for x in c if x['role']=='declared_reason')
  self.assertEqual(text[reason['start']:reason['end']],'data are missing')
  self.assertTrue(all(not x['condition_spans'] for x in c if x['end']<=text.index(';')))
  c,n=self.parsed('If invested, maintain exposure; review limits.')
  later=next(x for x in c if x['start']>len('If invested, maintain exposure;'))
  self.assertEqual(later['condition_spans'],[])

 def test_unsupported_postposed_if_clause_boundary_abstains(self):
  for text in ['Make no directional increase: if flat, do not initiate.', 'Maintain reserves, if uninvested, do not add risk.']:
   c,n=self.parsed(text)
   self.assertEqual(len(c),1);self.assertEqual(c[0]['role'],'conditional_envelope')
   self.assertEqual(c[0]['condition_spans'],[])
   self.assertIn('postposed_condition_clause_boundary_unresolved',n[0]['unresolved'])

 def test_all_current_typed_condition_links_stay_within_semicolon_branch(self):
  examined=0
  for clause in self.by['clauses_v3'].values():
   source=self.by['sources_v2'][clause['source_id']]
   n=self.by['propositions_v3'][clause['proposition_id']]['normalization']
   for guard in n['condition_spans']:
    examined+=1
    lo=min(clause['start'],guard['start'],guard['marker']['start']);hi=max(clause['end'],guard['end'],guard['marker']['end'])
    self.assertNotIn(';',source['text'][lo:hi])
    self.assertLessEqual(n['scope']['attachment_start'],lo);self.assertLessEqual(hi,n['scope']['attachment_end'])
  self.assertGreater(examined,0)

 def test_imperative_action_has_unknown_subject(self):
  c,n=self.parsed('If uninvested, do not initiate a position.')
  outcome=next(x for x in n if x['role']=='conditional_outcome')
  self.assertEqual(outcome['predicate']['text'],'initiate');self.assertIsNone(outcome['subject'])
  self.assertTrue(outcome['local_cues']['negation']);self.assertTrue(outcome['condition_spans'])
  self.assertEqual(outcome['slot_rule'],'R075')

 def test_attribution_is_not_market_fact_or_verified_support(self):
  c,n=self.parsed('Analyst Z says copper may rise.')
  self.assertEqual(n[0]['kind'],'attributed_statement_candidate');self.assertTrue(n[0]['inherited_frame_cues']['attribution'])
  self.assertFalse(n[0]['accepted_factual_support'])

 def test_unfamiliar_wording_does_not_require_run_or_known_quote(self):
  c,n=self.parsed('We retain copper because storage is scarce, not because headlines are optimistic.')
  self.assertTrue(any(x['role']=='declared_reason' for x in c));self.assertTrue(any(x['role']=='rejected_reason' for x in c))
  c,n=self.parsed('Unrecognized nominal fragment without a predicate.')
  self.assertIn('unsupported_predication',n[0]['unresolved'])

 def test_frame_partition_roundtrips_unicode_and_decimals(self):
  text='**Thesis**: Café demand is 1.25 units.\n\nIf held, do not add.  '
  f=rules.frames(text);self.assertEqual(''.join(text[a:b] for a,b,k,s in f),text)
  self.assertFalse(any(text[a:b]=='1.' for a,b,k,s in f))

 def test_decision_grains_direct_and_transitive_presence(self):
  self.assertEqual(len(self.by['packets_v3']),6)
  for p in self.by['packets_v3'].values():
   q=p['packet'];self.assertEqual(len(q['direct_input_presence_relation_ids']),5)
   self.assertEqual(len(q['measured_transfer_ancestry']),9)
   self.assertEqual(q['handoff_appearance_occurrences'],30);self.assertEqual(q['handoff_unique_endpoint_pairs'],26)
   self.assertEqual(q['direct_final_evidence_occurrences'],0)
   self.assertFalse(q['accepted_factual_support_relation_ids'])
   self.assertEqual(len(q['matched_clause_ids'])+len(q['unmatched_clause_ids']),len(q['rationale_clause_ids']))

 def test_handoff_provenance_failure_rejected(self):
  rows=list(self.rows)
  i=next(i for i,r in enumerate(rows) if r['table']=='typed_relations_v3' and r['relation']=='recorded_input_text_presence' and r['from_source_id'])
  rows[i]=copy.deepcopy(rows[i]);rows[i]['from_source_id']=next(s['id'] for s in self.by['sources_v2'].values() if s['run_id']!=self.by['sources_v2'][rows[i]['to_source_id']]['run_id'])
  with self.assertRaisesRegex(ValueError,'recipient mismatch'):validate(rows,False)

 def test_scope_and_application_tamper_rejected(self):
  rows=self.change('propositions_v3',lambda r:r['normalization']['inherited_frame_cues'].update(conditions=[{'text':'invented','start':0,'end':1}]))
  with self.assertRaises(ValueError):validate(rows,False)
  with self.assertRaisesRegex(ValueError,'input mismatch'):
   validate(self.change('applications_v3',lambda r:r.update(input_quote='invented')),False)

 def test_semantic_annotations_are_separate_authored_proposals(self):
  rows=[r for r in self.by['typed_relations_v3'].values() if r['relation']=='proposed_semantic_premise']
  self.assertEqual(len(rows),2)
  self.assertTrue(all(r['witness']['produced_by']=='hand_authored_interpretation_not_rule_discovered_relation' for r in rows))
  self.assertFalse(any(r['relation']=='accepted_factual_support' for r in self.by['typed_relations_v3'].values()))

 def test_unknown_clause_id_rejected_and_context_retains_parent(self):
  with closing(sqlite3.connect(DEST/'ledger.sqlite')) as db:
   db.row_factory=sqlite3.Row;c=next(iter(self.by['clauses_v3'].values()));result=clause_context(db,c['id'])
   self.assertIn(c['quote'],result['frame']['quote']);self.assertTrue(result['frame']['parent_passage_ids'])
   self.assertTrue(result['rule_applications'])
   with self.assertRaises(ValueError):clause_context(db,'stale-id')

 def test_standalone_rebuild_checks_all_parent_and_new_index_rows(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'v3.sqlite';rebuild(self.rows,path);validate_index(self.rows,path)
   with closing(sqlite3.connect(path)) as db,db:db.execute("UPDATE sources_v2 SET actor='tampered'")
   with self.assertRaisesRegex(ValueError,'Index rows mismatch'):validate_index(self.rows,path)

 def test_same_input_rule_annotation_environment_rebuild(self):
  cov=build();self.assertEqual(cov['canonical_sha256'],self.manifest['canonical_sha256'])
  self.assertEqual(cov['build_id'],self.manifest['build_id']);self.assertEqual(runtime(),self.manifest['runtime'])


if __name__=='__main__':unittest.main()
