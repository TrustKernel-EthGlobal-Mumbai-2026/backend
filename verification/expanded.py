"""Expanded offline corpus processing. Preserves the historical v1.1 parent."""
import argparse
import json
import re
import sqlite3
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from . import ledger as parent
from .corpus import inventory,appearances,summary as corpus_summary
from .processing import (VERSION,segments,classify,normalize,paragraph_bounds,explicit_numeric_fields,REASON,CONDITION,ASSUMPTION,cues)

ROOT=parent.ROOT
DEST=ROOT/'verification/data/expanded-v2'
VERSIONS=dict(schema_version=VERSION,normalization_version=VERSION,extraction_version=VERSION)
SPECS={
 'sources_v2': 'run_id TEXT actor TEXT stage TEXT source_type TEXT report_id TEXT call_id TEXT output_event_id TEXT anchor_event_id TEXT artifact_id TEXT pointer TEXT text TEXT sha256 TEXT content_group TEXT origin_method TEXT origin_pointer TEXT input_seq INTEGER output_seq INTEGER asserted_at TEXT',
 'outputs_v2': 'run_id TEXT actor TEXT event_id TEXT pointer TEXT source_id TEXT disposition TEXT details JSON',
 'appearances_v2': 'source_id TEXT run_id TEXT artifact_id TEXT event_id TEXT pointer TEXT start INTEGER end INTEGER appearance_type TEXT container_kind TEXT',
 'passages_v2': 'source_id TEXT start INTEGER end INTEGER text TEXT disposition TEXT tags JSON rule TEXT heading TEXT context_start INTEGER context_end INTEGER',
 'propositions_v2': 'source_id TEXT normalization JSON context JSON identity_status TEXT',
 'candidates_v2': 'source_id TEXT passage_id TEXT proposition_id TEXT parent_candidate_id TEXT start INTEGER end INTEGER quote TEXT candidate_kind TEXT atomization_status TEXT method TEXT provisional_status TEXT',
 'references_v2': 'source_id TEXT passage_id TEXT evidence_id TEXT start INTEGER end INTEGER quote TEXT form TEXT attachment TEXT status TEXT',
 'relations_v2': 'candidate_id TEXT source_id TEXT start INTEGER end INTEGER quote TEXT cue_start INTEGER cue_end INTEGER relation TEXT scope_status TEXT',
 'queue_v2': 'source_id TEXT passage_id TEXT candidate_id TEXT reason TEXT unresolved_fields JSON',
}
REFS={
 'source_id':'sources_v2','passage_id':'passages_v2','proposition_id':'propositions_v2','parent_candidate_id':'candidates_v2',
 'candidate_id':'candidates_v2','report_id':'reports','call_id':'calls','output_event_id':'events','anchor_event_id':'events',
 'artifact_id':'artifacts','event_id':'events','evidence_id':'evidence',
}
DISPOSITIONS={'candidate_assertion','conditional_guidance_hypothesis','question','background_structural_material','unresolved_interpretation','unprocessed_material'}
OPTIONAL={'sources_v2':{'report_id','anchor_event_id'},'outputs_v2':{'source_id'},'appearances_v2':{'event_id'},
          'candidates_v2':{'parent_candidate_id'},'references_v2':{'evidence_id'},'queue_v2':{'candidate_id'}}


def columns(table):
 parts=SPECS[table].split();return list(zip(parts[::2],parts[1::2]))


def schema_document():
 base=parent.schema_document();defs=base['$defs']
 for table in SPECS:
  properties={'table':{'const':table},'id':{'type':'string'},**{k:{'const':v} for k,v in VERSIONS.items()}}
  for name,kind in columns(table):
   types=['integer' if kind=='INTEGER' else 'string']
   if name in OPTIONAL.get(table,set()):types.append('null')
   properties[name]={} if kind=='JSON' else {'type':types}
  if table=='passages_v2':properties['disposition']={'enum':sorted(DISPOSITIONS)}
  defs[table]={'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
 return {'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:trustkernel:expanded-ledger:2.0.0',
         '$defs':defs,'oneOf':[{'$ref':'#/$defs/'+t} for t in [*parent.TABLES,*SPECS]]}


class Expansion:
 def __init__(self):self.tables={t:{} for t in SPECS}
 def add(self,table,identity,**values):
  key=parent.ident(table,identity)
  row=dict(table=table,id=key,**VERSIONS,**values)
  if set(values)!={n for n,_ in columns(table)}:raise ValueError('Unexpected fields '+table)
  if key in self.tables[table] and self.tables[table][key]!=row:raise ValueError('ID collision')
  self.tables[table][key]=row;return key
 def insert(self,table,row):
  row=dict(row);key=row.pop('id');self.tables[table][key]=dict(table=table,id=key,**VERSIONS,**row)
 def rows(self):return [r for t in sorted(self.tables) for _,r in sorted(self.tables[t].items())]


def process_source(exp,source,evidence):
 text=source['text'];sid=source['id']
 for left,right,heading in segments(text):
  quote=text[left:right]
  try:disposition,tags,rule=classify(quote,heading)
  except Exception as exc:disposition,tags,rule='unprocessed_material',[type(exc).__name__],'processing_failed_v2'
  ca,cb=paragraph_bounds(text,left,right)
  pid=exp.add('passages_v2',[sid,left,right],source_id=sid,start=left,end=right,text=quote,
              disposition=disposition,tags=tags,rule=rule,heading=heading,context_start=ca,context_end=cb)
  if disposition in ('unprocessed_material','unresolved_interpretation','question'):
   exp.add('queue_v2',[pid,disposition],source_id=sid,passage_id=pid,candidate_id=None,reason=disposition,unresolved_fields=['interpretation_or_premises'])
  candidate=None
  if disposition in ('candidate_assertion','conditional_guidance_hypothesis','unresolved_interpretation'):
   normalized=normalize(quote,left,disposition,tags)
   prop=exp.add('propositions_v2',[sid,pid,'surface'],source_id=sid,normalization=normalized,
                context={'run_id':source['run_id'],'actor':source['actor'],'source_type':source['source_type'],'source_scoped':True,
                         'assertion_time':source['asserted_at'],'valid_time_not_inferred_from_assertion_time':True},
                identity_status='unmerged_source_scoped_candidate')
   kind='surface_atom' if normalized['atomization_status'].startswith('surface_') else 'statement_envelope'
   candidate=exp.add('candidates_v2',[sid,pid,'surface'],source_id=sid,passage_id=pid,proposition_id=prop,parent_candidate_id=None,
                     start=left,end=right,quote=quote,candidate_kind=kind,atomization_status=normalized['atomization_status'],
                     method='reusable_surface_rules_2.0.0',provisional_status='candidate_not_semantically_verified')
   if normalized['unresolved_fields']:
    exp.add('queue_v2',[candidate,'normalization'],source_id=sid,passage_id=pid,candidate_id=candidate,reason='unresolved_normalization',unresolved_fields=normalized['unresolved_fields'])
   for pattern,relation in ((REASON,'author_reason_wording'),(CONDITION,'condition_wording'),(ASSUMPTION,'assumption_wording')):
    for cue in cues(pattern,quote,left):
     before=text[max(left,cue['start']-16):cue['start']]
     scope='negated_reason_marker_scope_unresolved_no_dependency_edge' if relation=='author_reason_wording' and re.search(r'\bnot\s+(?:merely\s+|just\s+)?$',before,re.I) else 'explicit_wording_scope_unresolved_no_dependency_edge'
     exp.add('relations_v2',[candidate,relation,cue['start']],candidate_id=candidate,source_id=sid,start=left,end=right,
             quote=text[left:right],relation=relation,scope_status=scope,cue_start=cue['start'],cue_end=cue['end'])
   for item in explicit_numeric_fields(quote,left):
    n=normalize(text[item['start']:item['end']],item['start'],disposition,[])
    n.update(predicate=item['predicate'],value=item['value'],conditions=normalized['conditions'],negation=normalized['negation'],modality=normalized['modality'],
             uncertainty=normalized['uncertainty'],unresolved_fields=['subject','valid_time','inherited_condition_negation_scope'],
             atomization_status='explicit_numeric_field_candidate')
    prop=exp.add('propositions_v2',[sid,pid,'numeric',item['start']],source_id=sid,normalization=n,
                 context={'parent_statement_candidate':candidate,'scope_inherited_from_full_passage':True},identity_status='unmerged_source_scoped_candidate')
    child=exp.add('candidates_v2',[sid,pid,'numeric',item['start']],source_id=sid,passage_id=pid,proposition_id=prop,parent_candidate_id=candidate,
                  start=item['start'],end=item['end'],quote=text[item['start']:item['end']],candidate_kind='explicit_numeric_field_atom',
                  atomization_status='explicit_numeric_field_candidate',method='explicit_numeric_field_2.0.0',provisional_status='candidate_not_semantically_verified')
    exp.add('queue_v2',[child,'normalization'],source_id=sid,passage_id=pid,candidate_id=child,reason='unresolved_normalization',unresolved_fields=n['unresolved_fields'])
  # References attach to a passage, never automatically to its candidate/children.
  known={e['evidence_key']:e['id'] for e in evidence}
  for m in re.finditer(r'\bE_[A-Z_]+\b|(?:fixture|https?)://[^\s<>\])`*]+',quote):
   token=m.group();eid=known.get(token)
   if token.startswith('fixture://'):
    eid=next((e['id'] for e in evidence if token.rstrip('.,;') in e['content']),None)
   exp.add('references_v2',[sid,left+m.start(),token],source_id=sid,passage_id=pid,evidence_id=eid,
           start=left+m.start(),end=left+m.end(),quote=token,form='literal_id' if token.startswith('E_') else 'uri',
           attachment='passage_mention_not_clause_support',status='explicit_text_reference_only')


def validate(rows,source_check=True):
 old=[r for r in rows if r['table'] in parent.TABLES];old_by=parent.validate_sources(old) if source_check else parent.validate_rows(old)
 by={t:{} for t in SPECS}
 for row in rows:
  if row['table'] in parent.TABLES:continue
  table=row['table']
  if table not in SPECS or row['id'] in by[table]:raise ValueError('Unknown table/duplicate ID')
  if set(row)!={'table','id',*VERSIONS,*(n for n,_ in columns(table))} or any(row[k]!=v for k,v in VERSIONS.items()):raise ValueError('Invalid expanded schema')
  for name,kind in columns(table):
   value=row[name]
   if value is None and name not in OPTIONAL.get(table,set()):raise ValueError('Missing expanded field '+name)
   if value is not None and kind!='JSON' and (type(value) is not int if kind=='INTEGER' else not isinstance(value,str)):raise ValueError('Invalid expanded type '+name)
  if table=='passages_v2' and row['disposition'] not in DISPOSITIONS:raise ValueError('Invalid disposition')
  by[table][row['id']]=row
 combined={**old_by,**by}
 for table,items in by.items():
  for row in items.values():
   for name,_ in columns(table):
    if name in REFS and row[name] is not None and row[name] not in combined[REFS[name]]:raise ValueError('Orphan '+table+'.'+name)
   if table=='sources_v2':
    if parent.sha(row['text'])!=row['sha256'] or row['sha256']!=row['content_group']:raise ValueError('Source content hash')
    call=old_by['calls'][row['call_id']];out=old_by['events'][row['output_event_id']]
    if call['end_event_id']!=out['id'] or call['actor']!=row['actor'] or call['run_id']!=row['run_id'] or out['seq']!=row['output_seq'] or out['timestamp']!=row['asserted_at'] or old_by['events'][call['start_event_id']]['seq']!=row['input_seq']:raise ValueError('Source actor/time origin mismatch')
    stage=old_by['events'][call['start_event_id']]['raw']['payload'].get('metadata',{}).get('metadata',{}).get('langgraph_node','recorded_stage_unavailable')
    if row['stage']!=stage:raise ValueError('Source recorded stage mismatch')
    if source_check:
     value=old_by['events'][row['anchor_event_id']]['raw'] if row['anchor_event_id'] else json.loads((ROOT/old_by['artifacts'][row['artifact_id']]['path']).read_text(encoding='utf-8'))
     if parent.resolve(value,row['pointer'])!=row['text']:raise ValueError('Source pointer round-trip')
    if row['report_id']:
     report=old_by['reports'][row['report_id']]
     if report['output_event_id']!=row['output_event_id'] or old_by['texts'][report['text_id']]['text']!=row['text']:raise ValueError('Report/source mismatch')
   if table=='outputs_v2':
    event=old_by['events'][row['event_id']]
    generation=parent.resolve(event['raw'],row['pointer'])
    if event['kind']!='llm.end' or row['run_id']!=event['run_id']:raise ValueError('Output inventory event mismatch')
    if row['disposition']=='originating_narrative':
     if not row['source_id'] or by['sources_v2'][row['source_id']]['output_event_id']!=row['event_id']:raise ValueError('Output/source inventory mismatch')
    elif row['source_id'] is not None or generation.get('text'):raise ValueError('Narrative excluded from inventory')
   if table in ('passages_v2','candidates_v2','references_v2','relations_v2'):
    source=by['sources_v2'][row['source_id']]
    quote=row['text'] if table=='passages_v2' else row['quote']
    if not 0<=row['start']<row['end']<=len(source['text']) or source['text'][row['start']:row['end']]!=quote:raise ValueError('Exact source span mismatch')
   if table=='candidates_v2':
    passage=by['passages_v2'][row['passage_id']]
    if passage['source_id']!=row['source_id'] or not passage['start']<=row['start']<row['end']<=passage['end']:raise ValueError('Candidate outside passage')
    if by['propositions_v2'][row['proposition_id']]['source_id']!=row['source_id']:raise ValueError('Proposition source mismatch')
    if row['parent_candidate_id'] and by['candidates_v2'][row['parent_candidate_id']]['passage_id']!=row['passage_id']:raise ValueError('Child scope lost')
   if table=='relations_v2' and not row['start']<=row['cue_start']<row['cue_end']<=row['end']:raise ValueError('Relation cue outside context')
   if table=='propositions_v2':
    text=by['sources_v2'][row['source_id']]['text'];n=row['normalization']
    for slot in ('subject','predicate','value'):
     value=n.get(slot)
     if value and text[value['start']:value['end']]!=value['text']:raise ValueError('Normalized slot span mismatch')
    for slot in ('numeric_expressions','units','time_expressions','negation','modality','conditions','uncertainty'):
     for value in n[slot]:
      if text[value['start']:value['end']]!=value['text']:raise ValueError('Cue span mismatch')
   if table=='appearances_v2' and source_check:
    source=by['sources_v2'][row['source_id']]
    if row['run_id']!=source['run_id']:raise ValueError('Cross-run appearance')
    value=old_by['events'][row['event_id']]['raw'] if row['event_id'] else json.loads((ROOT/old_by['artifacts'][row['artifact_id']]['path']).read_text(encoding='utf-8'))
    text=parent.resolve(value,row['pointer'])
    if text[row['start']:row['end']]!=source['text']:raise ValueError('Appearance source mismatch')
    if row['appearance_type']=='recorded_input_copy' and old_by['events'][row['event_id']]['seq']<=source['output_seq']:raise ValueError('Input copy precedes output')
 for source in by['sources_v2'].values():
  passages=sorted((p for p in by['passages_v2'].values() if p['source_id']==source['id']),key=lambda p:p['start'])
  cursor=0
  for passage in passages:
   if passage['start']!=cursor:raise ValueError('Passage gap/overlap')
   cursor=passage['end']
  if cursor!=len(source['text']):raise ValueError('Unaccounted source characters')
  if sum(a['source_id']==source['id'] and a['appearance_type']=='source_anchor' for a in by['appearances_v2'].values())!=1:raise ValueError('Missing/duplicate source anchor appearance')
 expected={(e['id'],f'/payload/response/generations/{i}/{j}') for e in old_by['events'].values() if e['kind']=='llm.end'
           for i,b in enumerate(e['raw']['payload']['response']['generations']) for j,g in enumerate(b)}
 actual={(o['event_id'],o['pointer']) for o in by['outputs_v2'].values()}
 if expected!=actual or len(actual)!=len(by['outputs_v2']):raise ValueError('Output inventory incomplete/duplicated')
 return combined


def coverage(exp,outputs,inventory_summary):
 result=dict(corpus=inventory_summary,versions=VERSIONS,counts={t:len(v) for t,v in exp.tables.items()},by_source=[])
 candidates=list(exp.tables['candidates_v2'].values());passages=list(exp.tables['passages_v2'].values())
 for source in exp.tables['sources_v2'].values():
  pp=[p for p in passages if p['source_id']==source['id']];cc=[c for c in candidates if c['source_id']==source['id']]
  chars=Counter()
  for p in pp:chars[p['disposition']]+=p['end']-p['start']
  result['by_source'].append(dict(source_id=source['id'],run_id=source['run_id'],actor=source['actor'],source_type=source['source_type'],
     characters=len(source['text']),accounted_characters=sum(chars.values()),passages=len(pp),disposition_characters=dict(chars),
     disposition_passages=dict(Counter(p['disposition'] for p in pp)),candidate_kinds=dict(Counter(c['candidate_kind'] for c in cc)),
     atomization_status=dict(Counter(c['atomization_status'] for c in cc))))
 result['totals']={
  'disposition_passages':dict(Counter(p['disposition'] for p in passages)),
  'disposition_characters':dict(sum((Counter(s['disposition_characters']) for s in result['by_source']),Counter())),
  'candidate_kinds':dict(Counter(c['candidate_kind'] for c in candidates)),
  'atomization_status':dict(Counter(c['atomization_status'] for c in candidates)),
  'unresolved_fields':dict(Counter(f for p in exp.tables['propositions_v2'].values() for f in p['normalization']['unresolved_fields'])),
  'unprocessed_characters':sum(p['end']-p['start'] for p in passages if p['disposition']=='unprocessed_material'),
  'semantically_verified_assertions':0,'semantic_recall':None,'semantic_atomization_completeness':None}
 result['warning']='Full passage accounting means each character has a processing disposition, not complete semantic extraction or verified truth. Candidate kinds overlap through explicit parent/child hierarchy; do not sum as unique facts.'
 return result


def rebuild(rows,path):
 validate(rows,False)
 old=[r for r in rows if r['table'] in parent.TABLES]
 parent.rebuild(old,path)
 with closing(sqlite3.connect(path)) as db:
  db.execute('PRAGMA foreign_keys=ON')
  for table in SPECS:
   defs=['id TEXT PRIMARY KEY',*(k+' TEXT NOT NULL' for k in VERSIONS)]
   defs += [n+' '+('TEXT' if t=='JSON' else t) for n,t in columns(table)]
   defs += [f'FOREIGN KEY({n}) REFERENCES {REFS[n]}(id) DEFERRABLE INITIALLY DEFERRED' for n,_ in columns(table) if n in REFS]
   db.execute('CREATE TABLE '+table+' ('+','.join(defs)+')')
  with db:
   for table in SPECS:
    names=['id',*VERSIONS,*(n for n,_ in columns(table))];j={n for n,t in columns(table) if t=='JSON'}
    records=[r for r in rows if r['table']==table]
    db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in names)+')',[[parent.canonical(r[n]) if n in j else r[n] for n in names] for r in records])
   db.execute('INSERT INTO ledger_metadata VALUES (?,?)',('expanded_sha256',parent.sha(''.join(parent.canonical(r)+'\n' for r in rows))))
  db.executescript('''
CREATE VIEW candidate_context_v2 AS SELECT c.*,s.run_id,s.actor,s.stage,s.source_type,s.asserted_at,s.input_seq,s.output_seq,p.disposition,p.tags,n.normalization FROM candidates_v2 c JOIN sources_v2 s ON s.id=c.source_id JOIN passages_v2 p ON p.id=c.passage_id JOIN propositions_v2 n ON n.id=c.proposition_id;
CREATE VIEW processing_coverage_v2 AS SELECT s.id source_id,s.run_id,s.actor,s.source_type,LENGTH(s.text) source_characters,p.disposition,COUNT(*) passages,SUM(p.end-p.start) characters FROM sources_v2 s JOIN passages_v2 p ON p.source_id=s.id GROUP BY s.id,p.disposition;
''')
  if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Expanded SQLite integrity')


def build():
 baseline,manifest=parent.validate_bundle('full')
 sources,outputs,by=inventory(baseline);copies=appearances(sources,by)
 exp=Expansion()
 for t,items in (('sources_v2',sources),('outputs_v2',outputs),('appearances_v2',copies)):
  for item in items:exp.insert(t,item)
 for source in sources:process_source(exp,source,list(by['evidence'].values()))
 rows=sorted(baseline+exp.rows(),key=lambda r:(r['table'],r['id']))
 validate(rows)
 DEST.mkdir(parents=True,exist_ok=True)
 content=''.join(parent.canonical(r)+'\n' for r in rows)
 (DEST/'ledger.jsonl').write_text(content,encoding='utf-8',newline='\n')
 rebuild(rows,DEST/'ledger.sqlite')
 cov=coverage(exp,outputs,corpus_summary(sources,outputs,copies))
 paths=[ROOT/'verification'/p for p in ('corpus.py','processing.py','expanded.py','expanded_query.py','EXPANSION_CONTRACT.md','tests/test_expanded.py')]
 hashes={p.relative_to(ROOT).as_posix():parent.sha(p.read_bytes()) for p in paths if p.exists()}
 build_id='expanded-v2-'+parent.sha(parent.canonical(dict(data=parent.sha(content),implementation=hashes)))[:20]
 cov.update(build_id=build_id,canonical_sha256=parent.sha(content),parent_build_id=manifest['build_id'])
 coverage_text=json.dumps(cov,indent=2,ensure_ascii=False)+'\n'
 (DEST/'coverage.json').write_text(coverage_text,encoding='utf-8',newline='\n')
 m=dict(build_id=build_id,versions=VERSIONS,canonical_sha256=parent.sha(content),coverage_sha256=parent.sha(coverage_text),
        parent_build_id=manifest['build_id'],parent_canonical_sha256=manifest['canonical_sha256'],rows=len(rows),new_counts=cov['counts'],implementation_hashes=hashes,
        extraction_method='reusable_local_surface_rules',external_inference_calls=0,independent_gold=False)
 m['preservation']={
  'historical_full_sha256':parent.sha((ROOT/'verification/data/full/ledger.jsonl').read_bytes()),
  'historical_pilot_sha256':parent.sha((ROOT/'verification/data/pilot/ledger.jsonl').read_bytes()),
  'historical_release_zip_sha256':parent.sha((ROOT/'verification/releases/TrustKernel-Atomic-Ledger-Draft-v1.1.zip').read_bytes())}
 (DEST/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8',newline='\n')
 (ROOT/'verification/expanded-schema.json').write_text(json.dumps(schema_document(),indent=2)+'\n',encoding='utf-8',newline='\n')
 lines=['# Expanded processing build', '',f'Build ID: `{build_id}`','',f'Canonical JSONL SHA-256: `{parent.sha(content)}`','',f'Parent build: `{manifest["build_id"]}`','',
        '| New table | Rows |','|---|---:|']
 lines += [f'| {t} | {n} |' for t,n in cov['counts'].items()]
 lines += ['',f'Source characters accounted: {cov["corpus"]["source_characters"]}; unprocessed: {cov["totals"]["unprocessed_characters"]}.',
           'Candidate kinds: `'+json.dumps(cov['totals']['candidate_kinds'])+'`.',
           'Full disposition accounting is not complete semantic extraction or verified truth. See coverage.json for per-source denominators and unresolved fields.','']
 (DEST/'BUILD.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
 return cov


def load_validate():
 data=(DEST/'ledger.jsonl').read_bytes();rows=[json.loads(l) for l in data.decode('utf-8').splitlines()]
 m=json.loads((DEST/'manifest.json').read_text(encoding='utf-8'))
 if parent.sha(data)!=m['canonical_sha256'] or parent.sha((DEST/'coverage.json').read_bytes())!=m['coverage_sha256']:raise ValueError('Expanded bundle hash mismatch')
 for filename,key in (('data/full/ledger.jsonl','historical_full_sha256'),('data/pilot/ledger.jsonl','historical_pilot_sha256'),('releases/TrustKernel-Atomic-Ledger-Draft-v1.1.zip','historical_release_zip_sha256')):
  if parent.sha((ROOT/'verification'/filename).read_bytes())!=m['preservation'][key]:raise ValueError('Historical release changed '+filename)
 for p,d in m['implementation_hashes'].items():
  if parent.sha((ROOT/p).read_bytes())!=d:raise ValueError('Implementation changed '+p)
 combined=validate(rows)
 with closing(sqlite3.connect((DEST/'ledger.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
  if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Index integrity')
  for table in SPECS:
   names=['id',*VERSIONS,*(n for n,_ in columns(table))];j={n for n,t in columns(table) if t=='JSON'}
   expected=[tuple(parent.canonical(r[n]) if n in j else r[n] for n in names) for _,r in sorted(combined[table].items())]
   if db.execute('SELECT '+','.join(names)+' FROM '+table+' ORDER BY id').fetchall()!=expected:raise ValueError('Index rows mismatch '+table)
 parent.validate_index([r for r in rows if r['table'] in parent.TABLES],DEST/'ledger.sqlite')
 return rows,m


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['build','validate','rebuild']);args=parser.parse_args()
 if args.command=='build':
  cov=build();print(json.dumps({k:cov[k] for k in ('build_id','counts','totals')},indent=2))
 elif args.command=='validate':
  rows,m=load_validate();print(m['build_id']+' PASS '+str(len(rows))+' rows')
 else:
  rows=[json.loads(l) for l in (DEST/'ledger.jsonl').read_text(encoding='utf-8').splitlines()];rebuild(rows,DEST/'ledger.sqlite');print('rebuild PASS')


if __name__=='__main__':main()
