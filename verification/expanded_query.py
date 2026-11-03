"""Read-only v2 candidate, condition, reason and unresolved processing queries."""
import argparse,json,sqlite3
from contextlib import closing
from .expanded import DEST

QUERIES={
 'coverage':'SELECT run_id,actor,source_type,disposition,SUM(characters) characters,SUM(passages) passages FROM processing_coverage_v2 GROUP BY run_id,actor,source_type,disposition ORDER BY run_id,actor,disposition',
 'unprocessed':"SELECT s.run_id,s.actor,s.source_type,p.* FROM passages_v2 p JOIN sources_v2 s ON s.id=p.source_id WHERE p.disposition='unprocessed_material' ORDER BY s.run_id,p.start",
 'unresolved':'SELECT s.run_id,s.actor,s.source_type,q.* FROM queue_v2 q JOIN sources_v2 s ON s.id=q.source_id ORDER BY s.run_id,s.actor,q.reason',
 'candidates':'SELECT id,run_id,actor,source_type,start,end,quote,candidate_kind,atomization_status,provisional_status FROM candidate_context_v2 ORDER BY run_id,output_seq,start',
 'conditions':"SELECT id,run_id,actor,source_type,quote,json_extract(normalization,'$.conditions') conditions,json_extract(normalization,'$.negation') negation,json_extract(normalization,'$.modality') modality FROM candidate_context_v2 WHERE json_array_length(normalization,'$.conditions')>0 OR json_array_length(normalization,'$.negation')>0 ORDER BY run_id,output_seq,start",
 'assumptions':"SELECT s.run_id,s.actor,s.source_type,r.* FROM relations_v2 r JOIN sources_v2 s ON s.id=r.source_id WHERE r.relation='assumption_wording' ORDER BY s.run_id,r.start",
 'decision_reasons':"SELECT s.run_id,s.actor,s.source_type,r.* FROM relations_v2 r JOIN sources_v2 s ON s.id=r.source_id WHERE r.relation='author_reason_wording' AND s.source_type IN ('investment_plan','trader_investment_plan','final_trade_decision','discussion') ORDER BY s.run_id,r.start",
 'references':'SELECT s.run_id,s.actor,s.source_type,r.* FROM references_v2 r JOIN sources_v2 s ON s.id=r.source_id ORDER BY s.run_id,r.start',
 'appearances':'SELECT s.run_id,s.actor,s.source_type,a.appearance_type,COUNT(*) appearances FROM appearances_v2 a JOIN sources_v2 s ON s.id=a.source_id GROUP BY s.id,a.appearance_type ORDER BY s.run_id,s.actor',
}


def context(db,candidate_id):
 row=db.execute('SELECT * FROM candidate_context_v2 WHERE id=?',(candidate_id,)).fetchone()
 if row is None:raise ValueError('Unknown candidate in this build; no stale-ID remapping')
 row=dict(row);row['normalization']=json.loads(row['normalization']);row['tags']=json.loads(row['tags'])
 source=dict(db.execute('SELECT * FROM sources_v2 WHERE id=?',(row['source_id'],)).fetchone())
 passage=dict(db.execute('SELECT * FROM passages_v2 WHERE id=?',(row['passage_id'],)).fetchone())
 return dict(candidate=row,source={k:v for k,v in source.items() if k!='text'},
             enclosing_paragraph=dict(start=passage['context_start'],end=passage['context_end'],text=source['text'][passage['context_start']:passage['context_end']]),
             text_references=[dict(r) for r in db.execute('SELECT * FROM references_v2 WHERE passage_id=?',(row['passage_id'],))],
             explicit_wording=[dict(r) for r in db.execute('SELECT * FROM relations_v2 WHERE candidate_id=?',(candidate_id,))],
             notice='Extraction candidate only. Text co-occurrence/reason wording does not establish factual support or a causal dependency.')


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',choices=[*QUERIES,'context'],default='coverage');p.add_argument('--candidate-id');p.add_argument('--limit',type=int,default=30);a=p.parse_args()
 if not 1<=a.limit<=10000:p.error('limit must be 1..10000')
 with closing(sqlite3.connect((DEST/'ledger.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
  if a.name=='context':
   if not a.candidate_id:p.error('context requires --candidate-id')
   result=context(db,a.candidate_id)
  else:result=[dict(r) for r in db.execute(QUERIES[a.name]+' LIMIT ?',(a.limit,))]
 m=json.loads((DEST/'manifest.json').read_text(encoding='utf-8'))
 print(json.dumps(dict(build_id=m['build_id'],query=a.name,result=result),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
