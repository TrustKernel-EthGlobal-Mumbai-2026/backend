"""Read-only inspection of v3 rules, decisions, scope and exact clause lineage."""
import argparse,json,sqlite3
from contextlib import closing
from .refined import DEST,ROOT

QUERIES={
 'decisions':"SELECT run_id,decision_source_id,json_array_length(packet,'$.rationale_clause_ids') rationale_children,json_array_length(packet,'$.matched_clause_ids') lexical_matched_children,json_array_length(packet,'$.unmatched_clause_ids') lexical_unmatched_children,json_extract(packet,'$.direct_final_evidence_occurrences') direct_evidence_occurrences FROM packets_v3 ORDER BY run_id",
 'source_map':'SELECT * FROM decision_source_map_v3 ORDER BY run_id,relation,relation_id',
 'ancestry_map':"SELECT p.run_id,s.actor,s.source_type,s.id source_id,json_extract(j.value,'$.depth') depth,json_extract(j.value,'$.path_relation_ids') presence_path FROM packets_v3 p,json_each(p.packet,'$.measured_transfer_ancestry') j JOIN sources_v2 s ON s.id=json_extract(j.value,'$.source_id') ORDER BY p.run_id,depth,s.actor",
 'evidence_paths':"SELECT p.run_id,s.actor,s.source_type,e.evidence_key,json_extract(j.value,'$.depth') depth,json_extract(j.value,'$.mode') presence_mode,json_extract(j.value,'$.relation_id') relation_id FROM packets_v3 p,json_each(p.packet,'$.evidence_occurrences') j JOIN sources_v2 s ON s.id=json_extract(j.value,'$.source_id') JOIN evidence e ON e.id=json_extract(j.value,'$.evidence_id') ORDER BY p.run_id,depth,s.actor,e.evidence_key",
 'literal_matches':'SELECT s.run_id,d.actor donor_actor,m.clause_id,m.start,m.end,m.quote,m.method FROM matches_v3 m JOIN sources_v2 s ON s.id=m.decision_source_id JOIN sources_v2 d ON d.id=m.donor_source_id ORDER BY s.run_id,m.start',
 'clauses':'SELECT id,run_id,actor,source_type,section,start,end,role,kind,quote FROM clause_context_v3 ORDER BY run_id,source_type,start',
 'reasons':"SELECT id,run_id,source_type,section,role,quote FROM clause_context_v3 WHERE role in ('declared_reason','rejected_reason','reason_polarity_unresolved') ORDER BY run_id,source_type,start",
 'conditions':"SELECT id,run_id,source_type,role,quote,json_extract(normalization,'$.condition_spans') explicit_conditions,json_extract(normalization,'$.inherited_frame_cues.conditions') inherited_markers FROM clause_context_v3 WHERE kind='conditional_component' ORDER BY run_id,start",
 'unresolved':'SELECT s.run_id,s.actor,s.source_type,q.* FROM queue_v3 q JOIN sources_v2 s ON s.id=q.source_id ORDER BY s.run_id,s.actor',
 'applications':'SELECT s.run_id,s.actor,a.* FROM applications_v3 a JOIN sources_v2 s ON s.id=a.source_id ORDER BY s.run_id,a.input_start',
 'annotations':"SELECT * FROM typed_relations_v3 WHERE relation='proposed_semantic_premise' ORDER BY id",
 'relations':'SELECT relation,method,status,COUNT(*) occurrences FROM typed_relations_v3 GROUP BY relation,method,status ORDER BY relation,method,status',
}


def clause_context(db,cid):
 row=db.execute('SELECT * FROM clause_context_v3 WHERE id=?',(cid,)).fetchone()
 if row is None:raise ValueError('Unknown v3 clause ID; no stale-ID rebinding')
 row=dict(row);row['normalization']=json.loads(row['normalization'])
 source=dict(db.execute('SELECT * FROM sources_v2 WHERE id=?',(row['source_id'],)).fetchone())
 frame=dict(db.execute('SELECT * FROM frames_v3 WHERE id=?',(row['frame_id'],)).fetchone())
 for key in ('parent_passage_ids','parent_candidate_ids'):frame[key]=json.loads(frame[key])
 applications=[dict(r) for r in db.execute('SELECT * FROM applications_v3 WHERE clause_id=?',(cid,))]
 for a in applications:
  for key in ('rule_ids','output_fields','unresolved'):a[key]=json.loads(a[key])
 return {'clause':row,'frame':frame,'paragraph':source['text'][frame['paragraph_start']:frame['paragraph_end']],
         'source':{k:v for k,v in source.items() if k!='text'},'rule_applications':applications,
         'notice':'Every slot is provisional surface interpretation. Conditions/context are retained; source presence and accepted support are different.'}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',choices=[*QUERIES,'packet','context','registry'],default='decisions');p.add_argument('--run-id');p.add_argument('--clause-id');p.add_argument('--limit',type=int,default=30);a=p.parse_args()
 if not 1<=a.limit<=10000:p.error('limit must be 1..10000')
 with closing(sqlite3.connect((DEST/'ledger.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
  if a.name=='context':
   if not a.clause_id:p.error('context requires --clause-id')
   result=clause_context(db,a.clause_id)
  elif a.name=='packet':
   if not a.run_id:p.error('packet requires --run-id')
   row=db.execute('SELECT packet FROM packets_v3 WHERE run_id=?',(a.run_id,)).fetchone()
   if not row:raise ValueError('Unknown recorded decision')
   result=json.loads(row[0])
  elif a.name=='registry':result=json.loads((ROOT/'verification/refinement_rules.json').read_text(encoding='utf-8'))
  else:result=[dict(r) for r in db.execute(QUERIES[a.name]+' LIMIT ?',(a.limit,))]
 manifest=json.loads((DEST/'manifest.json').read_text(encoding='utf-8'))
 print(json.dumps({'build_id':manifest['build_id'],'query':a.name,'result':result},indent=2,ensure_ascii=False))


if __name__=='__main__':main()
