"""Separate v3 refinement/traceability overlay; accepted historical releases are inputs."""
import argparse,difflib,json,platform,re,sqlite3,sys,unicodedata
from collections import Counter,defaultdict,deque
from contextlib import closing
from pathlib import Path
from . import ledger as base
from . import expanded as v2
from . import refine_rules as rules

ROOT=base.ROOT;DEST=ROOT/'verification/data/refined-v3';VERSION='3.0.1'
VERSIONS=dict(schema_version='3.0.0',normalization_version=VERSION,extraction_version=VERSION)
PRIORITY={'final_trade_decision','investment_plan','trader_investment_plan'}
SPECS={
 'scope_v3':'source_id TEXT priority INTEGER reasons JSON',
 'frames_v3':'source_id TEXT start INTEGER end INTEGER quote TEXT frame_kind TEXT section TEXT paragraph_start INTEGER paragraph_end INTEGER parent_passage_ids JSON parent_candidate_ids JSON',
 'clauses_v3':'source_id TEXT frame_id TEXT proposition_id TEXT start INTEGER end INTEGER quote TEXT role TEXT kind TEXT status TEXT',
 'propositions_v3':'source_id TEXT normalization JSON identity_status TEXT',
 'applications_v3':'source_id TEXT frame_id TEXT clause_id TEXT rule_ids JSON input_start INTEGER input_end INTEGER input_quote TEXT output_fields JSON unresolved JSON',
 'queue_v3':'source_id TEXT frame_id TEXT clause_id TEXT reasons JSON',
 'actor_mentions_v3':'source_id TEXT target_source_id TEXT actor TEXT start INTEGER end INTEGER quote TEXT status TEXT',
 'typed_relations_v3':'from_source_id TEXT to_source_id TEXT evidence_id TEXT clause_id TEXT relation TEXT method TEXT status TEXT witness JSON',
 'matches_v3':'decision_source_id TEXT clause_id TEXT donor_source_id TEXT appearance_id TEXT start INTEGER end INTEGER quote TEXT input_event_id TEXT input_pointer TEXT input_start INTEGER input_end INTEGER method TEXT',
 'packets_v3':'decision_source_id TEXT run_id TEXT packet JSON',
}
REFS={'source_id':'sources_v2','from_source_id':'sources_v2','to_source_id':'sources_v2','decision_source_id':'sources_v2','donor_source_id':'sources_v2','target_source_id':'sources_v2',
      'frame_id':'frames_v3','clause_id':'clauses_v3','proposition_id':'propositions_v3','evidence_id':'evidence','appearance_id':'appearances_v2','input_event_id':'events'}
RELATIONS={'exact_origin','recorded_input_text_presence','recorded_input_evidence_presence','explicit_citation','explicit_stated_reason','proposed_semantic_premise','conditional_numeric_check','accepted_factual_support'}


def columns(t):
 parts=SPECS[t].split();return list(zip(parts[::2],parts[1::2]))


class Layer:
 def __init__(self):self.tables={t:{} for t in SPECS}
 def add(self,t,identity,**values):
  key=base.ident(t,identity)
  if set(values)!={n for n,k in columns(t)}:raise ValueError('Schema '+t)
  row=dict(table=t,id=key,**VERSIONS,**values)
  if key in self.tables[t] and self.tables[t][key]!=row:raise ValueError('ID collision')
  self.tables[t][key]=row;return key
 def rows(self):return [r for t in sorted(self.tables) for _,r in sorted(self.tables[t].items())]


def group(rows):
 result=defaultdict(dict)
 for r in rows:result[r['table']][r['id']]=r
 return result


def scope_sources(layer,by,registry):
 sources=by['sources_v2'];priority=[s for s in sources.values() if s['source_type'] in PRIORITY];reasons=defaultdict(list)
 for s in priority:reasons[s['id']].append({'rule':'S001','reason':'priority_decision_investment_trader'})
 for candidate in by['candidates_v2'].values():
  value=by['propositions_v2'][candidate['proposition_id']]['normalization'].get('value')
  if sources[candidate['source_id']]['source_type']=='discussion' and value and not re.search(r'\w',value['text']):
   reasons[candidate['source_id']].append({'rule':'S002','reason':'legacy_punctuation_only_slot_regression','parent_candidate_id':candidate['id']})
 for s in priority:
  for actor,aliases in registry['actor_aliases'].items():
   pattern=re.compile(r'\b(?:'+'|'.join(re.escape(a) for a in sorted(aliases,key=len,reverse=True))+r')s?\b',re.I)
   target=next((x for x in sources.values() if x['run_id']==s['run_id'] and x['actor']==actor and x['source_type']=='discussion' and x['output_seq']<s['output_seq']),None)
   for m in pattern.finditer(s['text']):
    layer.add('actor_mentions_v3',[s['id'],actor,m.start()],source_id=s['id'],target_source_id=target['id'] if target else None,actor=actor,
              start=m.start(),end=m.end(),quote=m.group(),status='explicit_role_mention_not_quote_support_or_reliance')
    if target:reasons[target['id']].append({'rule':'S001','reason':'named_discussion_role','referring_source_id':s['id'],'span':[m.start(),m.end()]})
 for sid,why in sorted(reasons.items()):layer.add('scope_v3',sid,source_id=sid,priority=int(sources[sid]['source_type'] in PRIORITY),reasons=why)
 return [sources[sid] for sid in sorted(reasons)]


def refine_source(layer,source,by):
 text=source['text'];sid=source['id']
 for a,b,kind,section in rules.frames(text):
  pa,pb=base_bounds(text,a,b)
  pp=[p['id'] for p in by['passages_v2'].values() if p['source_id']==sid and p['start']<b and a<p['end']]
  pc=[c['id'] for c in by['candidates_v2'].values() if c['source_id']==sid and c['start']<b and a<c['end']]
  fid=layer.add('frames_v3',[sid,a,b],source_id=sid,start=a,end=b,quote=text[a:b],frame_kind=kind,section=section,
                paragraph_start=pa,paragraph_end=pb,parent_passage_ids=pp,parent_candidate_ids=pc)
  if kind!='sentence_frame':
   layer.add('applications_v3',[fid,'metadata'],source_id=sid,frame_id=fid,clause_id=None,rule_ids=['R010'] if kind=='section_metadata' else ['R020'],input_start=a,input_end=b,input_quote=text[a:b],output_fields={'disposition':kind,'section':section,'semantic_predicate':None},unresolved=[])
   continue
  children=rules.decompose(text,a,b)
  if section.lower() in rules.SCALAR_SECTIONS:
   children=[dict(start=a,end=b,role='scalar_declaration',rule='R010',connector=None,condition_spans=[],extra=['scalar_report_field_not_semantic_predication'])]
  for child in children:
   n=rules.normalization(text,child,a,b,pa,pb)
   prop=layer.add('propositions_v3',[sid,fid,child['start'],child['end'],child['role']],source_id=sid,normalization=n,identity_status='unmerged_provisional_source_scoped')
   cid=layer.add('clauses_v3',[sid,fid,child['start'],child['end'],child['role']],source_id=sid,frame_id=fid,proposition_id=prop,
                 start=child['start'],end=child['end'],quote=text[child['start']:child['end']],role=child['role'],kind=n['kind'],status='provisional_rule_structure_not_verified_truth')
   rid=['R020']+([child['boundary_rule']] if child.get('boundary_rule') else [])+[child['rule']]
   if child['rule']!='R030':rid.append(n['slot_rule'])
   if n['unresolved']:rid.append('R090')
   layer.add('applications_v3',[cid,'rules'],source_id=sid,frame_id=fid,clause_id=cid,rule_ids=list(dict.fromkeys(rid)),input_start=a,input_end=b,input_quote=text[a:b],output_fields=n,unresolved=n['unresolved'])
   if n['unresolved']:layer.add('queue_v3',cid,source_id=sid,frame_id=fid,clause_id=cid,reasons=n['unresolved'])
   if child['role'] in ('declared_reason','rejected_reason','reason_polarity_unresolved'):
    layer.add('typed_relations_v3',[cid,'reason'],from_source_id=sid,to_source_id=None,evidence_id=None,clause_id=cid,relation='explicit_stated_reason',method='R040',
              status=child['role'],witness={'frame_id':fid,'marker':child['connector'],'full_context':[a,b],'not_a_validated_cause_or_sufficient_premise':True})


def base_bounds(text,a,b):
 left=text.rfind('\n\n',0,a);right=text.find('\n\n',b)
 return 0 if left<0 else left+2,len(text) if right<0 else right


def connect_recordings(layer,by):
 sources=by['sources_v2'];call_sources={s['call_id']:s for s in sources.values()};start_sources={by['calls'][s['call_id']]['start_event_id']:s for s in sources.values()}
 for s in sources.values():
  layer.add('typed_relations_v3',[s['id'],'origin'],from_source_id=s['id'],to_source_id=None,evidence_id=None,clause_id=None,relation='exact_origin',method=s['origin_method'],status='source_join_verified_only',
            witness={k:s[k] for k in ('artifact_id','pointer','origin_pointer','output_event_id','call_id','asserted_at','input_seq','output_seq')})
 calls_by_start={c['start_event_id']:c for c in by['calls'].values()}
 for app in by['appearances_v2'].values():
  if app['appearance_type']!='recorded_input_copy':continue
  recipient=start_sources.get(app['event_id']);donor=sources[app['source_id']];start=by['events'][app['event_id']]
  if start['run_id']!=donor['run_id'] or donor['output_seq']>=start['seq']:raise ValueError('Invalid time/run handoff')
  layer.add('typed_relations_v3',[app['id'],'presence'],from_source_id=recipient['id'] if recipient else None,to_source_id=donor['id'],evidence_id=None,clause_id=None,
            relation='recorded_input_text_presence',method='T010',status='exact_copy_presence_not_causal_reliance' if recipient else 'input_copy_at_call_without_originating_narrative',
            witness={'appearance_id':app['id'],'receiving_call_id':calls_by_start[app['event_id']]['id'],'receiving_input_event_id':app['event_id'],'input_pointer':app['pointer'],'input_span':[app['start'],app['end']]})
 for exposure in by['exposures'].values():
  if not exposure['evidence_id']:continue
  recipient=call_sources.get(exposure['call_id'])
  layer.add('typed_relations_v3',[exposure['id'],'evidence'],from_source_id=recipient['id'] if recipient else None,to_source_id=None,evidence_id=exposure['evidence_id'],clause_id=None,
            relation='recorded_input_evidence_presence',method=exposure['mode'],status='presence_at_named_call_only',witness={'receiving_call_id':exposure['call_id'],'exposure_id':exposure['id'],'text_id':exposure['text_id'],'provenance':exposure['provenance']})
 for ref in by['references_v2'].values():
  layer.add('typed_relations_v3',[ref['id'],'citation'],from_source_id=ref['source_id'],to_source_id=None,evidence_id=ref['evidence_id'],clause_id=None,
            relation='explicit_citation',method='parent_lexical_reference',status='mention_only_not_clause_support',witness={'reference_id':ref['id'],'span':[ref['start'],ref['end']],'quote':ref['quote'],'attachment':ref['attachment']})
 report_sources={s['report_id']:s for s in sources.values() if s['report_id']}
 for check in by['checks'].values():
  if check['category']!='conditional_fixture_comparison':continue
  assertion=by['assertions'][check['subject_id']];source=report_sources[assertion['report_id']]
  layer.add('typed_relations_v3',[check['id'],'conditional'],from_source_id=source['id'],to_source_id=None,evidence_id=check['details']['evidence_id'],clause_id=None,
            relation='conditional_numeric_check',method=check['method'],status='parent_check_conditional_on_original_mapping',witness={'check_id':check['id'],'assertion_id':assertion['id'],'result':check['result'],'details':check['details']})


def apply_annotations(layer,by,overlay):
 for a in overlay['annotations']:
  f=next(s for s in by['sources_v2'].values() if s['run_id']==a['run_id'] and s['source_type']==a['from_type'])
  t=next(s for s in by['sources_v2'].values() if s['run_id']==a['run_id'] and s['source_type']==a['to_type'])
  fp=list(base.matches(f['text'],a['from_quote']));tp=list(base.matches(t['text'],a['to_quote']))
  if len(fp)!=1 or len(tp)!=1:raise ValueError('Annotation anchor missing/ambiguous '+a['id'])
  layer.add('typed_relations_v3',[a['id'],overlay['annotation_version']],from_source_id=f['id'],to_source_id=t['id'],evidence_id=None,clause_id=None,
            relation='proposed_semantic_premise',method='A010_anchor_validation_only',status=overlay['status'],
            witness={'annotation_id':a['id'],'annotation_version':overlay['annotation_version'],'author':overlay['author'],'from_span':list(fp[0]),'to_span':list(tp[0]),
                     'from_quote':a['from_quote'],'to_quote':a['to_quote'],'interpretation':a['interpretation'],'produced_by':'hand_authored_interpretation_not_rule_discovered_relation'})


def ancestors(layer,decision):
 edges=sorted([e for e in layer.tables['typed_relations_v3'].values() if e['relation']=='recorded_input_text_presence'],key=lambda e:e['id'])
 adjacency=defaultdict(list)
 for e in edges:adjacency[e['from_source_id']].append(e)
 paths={decision['id']:[]};queue=deque([decision['id']])
 while queue:
  node=queue.popleft()
  for edge in sorted(adjacency[node],key=lambda e:e['id']):
   to=edge['to_source_id']
   if to not in paths:paths[to]=paths[node]+[edge['id']];queue.append(to)
 relevant=[e for e in edges if e['from_source_id'] in paths and e['to_source_id'] in paths]
 return paths,relevant


def literal_matches(layer,by,decision,registry):
 call=by['calls'][decision['call_id']];input_id=call['start_event_id']
 direct=[a for a in by['appearances_v2'].values() if a['event_id']==input_id and a['appearance_type']=='recorded_input_copy']
 clauses=sorted([c for c in layer.tables['clauses_v3'].values() if c['source_id']==decision['id'] and layer.tables['frames_v3'][c['frame_id']]['section'].lower() in ('investment thesis','executive summary')],key=lambda c:(c['start'],c['end'],c['id']))
 for c in clauses:
  for appearance in direct:
   donor=by['sources_v2'][appearance['source_id']];text=donor['text'];blocks=[]
   for a,b in base.matches(text,c['quote']):blocks.append((0,len(c['quote']),a,b,'whole_clause_literal_match'))
   if not blocks:
    matcher=difflib.SequenceMatcher(None,c['quote'],text,autojunk=False)
    for block in matcher.get_matching_blocks():
     quote=c['quote'][block.a:block.a+block.size]
     if block.size>=registry['overlap_min_characters'] and len(re.findall(r'\w+',quote))>=registry['overlap_min_word_tokens']:
      blocks.append((block.a,block.a+block.size,block.b,block.b+block.size,'exact_contiguous_wording_overlap'))
   for ca,cb,da,db,method in blocks:
    left=c['start']+ca;right=c['start']+cb
    layer.add('matches_v3',[c['id'],appearance['id'],left,right,da,method],decision_source_id=decision['id'],clause_id=c['id'],donor_source_id=donor['id'],appearance_id=appearance['id'],
              start=left,end=right,quote=decision['text'][left:right],input_event_id=input_id,input_pointer=appearance['pointer'],input_start=appearance['start']+da,input_end=appearance['start']+db,method=method)
 return clauses


def intervals(points):
 result=[]
 for p in sorted(points):
  if not result or p!=result[-1][1]:result.append([p,p+1])
  else:result[-1][1]=p+1
 return result


def make_packets(layer,by,registry):
 rels=sorted(layer.tables['typed_relations_v3'].values(),key=lambda e:e['id'])
 for decision in sorted((s for s in by['sources_v2'].values() if s['source_type']=='final_trade_decision'),key=lambda s:s['run_id']):
  paths,edges=ancestors(layer,decision);cc=literal_matches(layer,by,decision,registry)
  matches=sorted([m for m in layer.tables['matches_v3'].values() if m['decision_source_id']==decision['id']],key=lambda m:m['id'])
  frames=[f for f in layer.tables['frames_v3'].values() if f['source_id']==decision['id'] and f['frame_kind']=='sentence_frame' and f['section'].lower() in ('investment thesis','executive summary')]
  denominator={i for f in frames for i in range(f['start'],f['end'])};covered={i for m in matches for i in range(m['start'],m['end'])}&denominator
  matched_ids={m['clause_id'] for m in matches}
  evidence=[dict(relation_id=e['id'],source_id=e['from_source_id'],depth=len(paths[e['from_source_id']]),path_relation_ids=paths[e['from_source_id']],evidence_id=e['evidence_id'],mode=e['method']) for e in rels if e['relation']=='recorded_input_evidence_presence' and e['from_source_id'] in paths]
  citations=[e['id'] for e in rels if e['relation']=='explicit_citation' and e['from_source_id'] in paths]
  numeric=[e['id'] for e in rels if e['relation']=='conditional_numeric_check' and e['from_source_id'] in paths]
  packet=dict(run_id=decision['run_id'],decision_source_id=decision['id'],origin={k:decision[k] for k in ('artifact_id','pointer','origin_method','origin_pointer','output_event_id','call_id','input_seq','output_seq','asserted_at')},
              direct_input_presence_relation_ids=[e['id'] for e in edges if e['from_source_id']==decision['id']],
              handoff_appearance_occurrences=len(edges),handoff_unique_endpoint_pairs=len({(e['from_source_id'],e['to_source_id']) for e in edges}),
              measured_transfer_ancestry=[dict(source_id=sid,depth=len(path),path_relation_ids=path) for sid,path in sorted(paths.items()) if sid!=decision['id']],
              handoff_relation_ids=[e['id'] for e in edges],rationale_clause_ids=[c['id'] for c in cc],matched_clause_ids=sorted(matched_ids),
              unmatched_clause_ids=sorted(c['id'] for c in cc if c['id'] not in matched_ids),literal_match_ids=[m['id'] for m in matches],
              literal_matching_method={'rule':'T020','min_partial_characters':registry['overlap_min_characters'],'min_partial_word_tokens':registry['overlap_min_word_tokens'],'case_sensitive':True,'whole_clause_match_separate':True},
              rationale_character_denominator=len(denominator),matched_literal_characters=len(covered),unmatched_literal_spans=intervals(denominator-covered),
              evidence_occurrences=evidence,direct_final_evidence_occurrences=sum(e['depth']==0 for e in evidence),
              citation_relation_ids=citations,conditional_numeric_check_relation_ids=numeric,
              stated_reason_relation_ids=[e['id'] for e in rels if e['relation']=='explicit_stated_reason' and e['from_source_id']==decision['id']],
              proposed_semantic_premise_relation_ids=[e['id'] for e in rels if e['relation']=='proposed_semantic_premise' and e['from_source_id']==decision['id']],
              accepted_factual_support_relation_ids=[],gaps=['Exact input/copy ancestry shows observable transfers, not reliance or sufficiency.','Upstream evidence exposure is not direct final-call evidence delivery.','Unmatched literal wording may be paraphrased/partial; absence is not unsupportedness.','Actor mention is attribution, not clause-level quotation support.','Conditional numeric checks remain on their original upstream claims; no automatic final-decision support.','No independent semantic validation or accepted factual-support policy is established.'])
  layer.add('packets_v3',decision['id'],decision_source_id=decision['id'],run_id=decision['run_id'],packet=packet)


def validate(rows,source_check=True):
 old=[r for r in rows if r['table'] not in SPECS];by=v2.validate(old,source_check);new={t:{} for t in SPECS}
 for row in rows:
  if row['table'] not in SPECS:continue
  t=row['table']
  if row['id'] in new[t] or set(row)!={'id','table',*VERSIONS,*(n for n,k in columns(t))} or any(row[k]!=v for k,v in VERSIONS.items()):raise ValueError('Invalid v3 row')
  new[t][row['id']]=row
 allby={**by,**new}
 for t,items in new.items():
  for row in items.values():
   for name,k in columns(t):
    if name in REFS and row[name] is not None and row[name] not in allby[REFS[name]]:raise ValueError('Orphan v3 '+name)
   if t in ('frames_v3','clauses_v3','actor_mentions_v3'):
    s=by['sources_v2'][row['source_id']]
    if not 0<=row['start']<row['end']<=len(s['text']) or s['text'][row['start']:row['end']]!=row['quote']:raise ValueError('V3 span mismatch')
   if t=='frames_v3':
    for pid in row['parent_passage_ids']:
     p=by['passages_v2'][pid]
     if p['source_id']!=row['source_id'] or not p['start']<row['end'] or not row['start']<p['end']:raise ValueError('Parent envelope mismatch')
   if t=='clauses_v3':
    f=new['frames_v3'][row['frame_id']]
    if f['source_id']!=row['source_id'] or not f['start']<=row['start']<row['end']<=f['end']:raise ValueError('Clause outside frame')
    n=new['propositions_v3'][row['proposition_id']]['normalization'];s=by['sources_v2'][row['source_id']]
    for key in ('subject','predicate','value'):
     x=n[key]
     if x and (s['text'][x['start']:x['end']]!=x['text'] or not re.search(r'\w',x['text'])):raise ValueError('Invalid normalized slot')
    if n['accepted_factual_support'] is not False:raise ValueError('Extraction cannot accept factual support')
    for groupname in ('local_cues','inherited_frame_cues'):
     for values in n[groupname].values():
      for x in values:
       if s['text'][x['start']:x['end']]!=x['text']:raise ValueError('Inherited/local cue mismatch')
    declared_children=rules.decompose(s['text'],f['start'],f['end'])
    if f['section'].lower() in rules.SCALAR_SECTIONS:declared_children=[dict(start=f['start'],end=f['end'],role='scalar_declaration',rule='R010',connector=None,condition_spans=[],extra=['scalar_report_field_not_semantic_predication'])]
    child=next((c for c in declared_children if c['start']==row['start'] and c['end']==row['end'] and c['role']==row['role']),None)
    if child is None:raise ValueError('Clause not produced by declared rules')
    if rules.condition_attachment_issues(s['text'],child,f['start'],f['end']):raise ValueError('Condition attachment crosses branch boundary')
    expected=rules.normalization(s['text'],child,f['start'],f['end'],f['paragraph_start'],f['paragraph_end'])
    if expected!=n:raise ValueError('Rule normalization mismatch/dropped inherited scope')
   if t=='applications_v3':
    source=by['sources_v2'][row['source_id']];f=new['frames_v3'][row['frame_id']]
    if row['input_start']!=f['start'] or row['input_end']!=f['end'] or source['text'][row['input_start']:row['input_end']]!=row['input_quote']:raise ValueError('Rule application input mismatch')
    if row['clause_id']:
     c=new['clauses_v3'][row['clause_id']];n=new['propositions_v3'][c['proposition_id']]['normalization']
     if row['output_fields']!=n or row['unresolved']!=n['unresolved']:raise ValueError('Rule application output mismatch')
   if t=='typed_relations_v3':
    if row['relation'] not in RELATIONS or row['relation']=='accepted_factual_support':raise ValueError('Unestablished relation/support')
    if row['relation']=='recorded_input_text_presence':
     app=by['appearances_v2'][row['witness']['appearance_id']];call=by['calls'][row['witness']['receiving_call_id']];donor=by['sources_v2'][row['to_source_id']];start=by['events'][call['start_event_id']]
     if app['source_id']!=donor['id'] or app['event_id']!=call['start_event_id'] or donor['run_id']!=call['run_id'] or donor['output_seq']>=start['seq']:raise ValueError('Invalid handoff provenance/time')
     if row['from_source_id'] and by['sources_v2'][row['from_source_id']]['call_id']!=call['id']:raise ValueError('Handoff recipient mismatch')
    if row['relation']=='recorded_input_evidence_presence':
     x=by['exposures'][row['witness']['exposure_id']]
     if x['evidence_id']!=row['evidence_id'] or x['call_id']!=row['witness']['receiving_call_id'] or x['mode']!=row['method']:raise ValueError('Evidence presence provenance mismatch')
     if row['from_source_id'] and by['sources_v2'][row['from_source_id']]['call_id']!=x['call_id']:raise ValueError('Evidence presence wrong recipient')
    if row['relation']=='explicit_citation':
     ref=by['references_v2'][row['witness']['reference_id']]
     if ref['source_id']!=row['from_source_id'] or ref['evidence_id']!=row['evidence_id']:raise ValueError('Citation provenance mismatch')
    if row['relation']=='conditional_numeric_check':
     check=by['checks'][row['witness']['check_id']];claim=by['assertions'][check['subject_id']]
     if by['sources_v2'][row['from_source_id']]['report_id']!=claim['report_id'] or check['category']!='conditional_fixture_comparison':raise ValueError('Check incorrectly assigned to decision')
    if row['relation']=='proposed_semantic_premise':
     if row['witness'].get('produced_by')!='hand_authored_interpretation_not_rule_discovered_relation':raise ValueError('Annotation authorship lost')
     for side,key in [('from','from_source_id'),('to','to_source_id')]:
      a,b=row['witness'][side+'_span']
      if by['sources_v2'][row[key]]['text'][a:b]!=row['witness'][side+'_quote']:raise ValueError('Annotation anchor mismatch')
     f=by['sources_v2'][row['from_source_id']];target=by['sources_v2'][row['to_source_id']]
     if f['run_id']!=target['run_id'] or target['output_seq']>=f['input_seq']:raise ValueError('Proposed premise crosses run/time')
   if t=='matches_v3':
    s=by['sources_v2'][row['decision_source_id']];event=by['events'][row['input_event_id']]
    value=base.resolve(event['raw'],row['input_pointer'])
    if s['text'][row['start']:row['end']]!=row['quote'] or value[row['input_start']:row['input_end']]!=row['quote']:raise ValueError('Literal match round-trip')
    app=by['appearances_v2'][row['appearance_id']]
    if app['source_id']!=row['donor_source_id'] or app['event_id']!=row['input_event_id']:raise ValueError('Literal match source provenance')
    if by['calls'][s['call_id']]['start_event_id']!=row['input_event_id']:raise ValueError('Literal match not in this decision input')
 for scope in new['scope_v3'].values():
  source=by['sources_v2'][scope['source_id']];fs=sorted([f for f in new['frames_v3'].values() if f['source_id']==source['id']],key=lambda f:f['start']);cursor=0
  for f in fs:
   if f['start']!=cursor:raise ValueError('Refinement frame gap/overlap')
   cursor=f['end']
  if cursor!=len(source['text']):raise ValueError('Unprocessed refinement source characters')
 if {p['decision_source_id'] for p in new['packets_v3'].values()}!={s['id'] for s in by['sources_v2'].values() if s['source_type']=='final_trade_decision'}:raise ValueError('Decision packet coverage')
 if any(p['packet']['accepted_factual_support_relation_ids'] for p in new['packets_v3'].values()):raise ValueError('Unestablished accepted support')
 if source_check:
  registry=json.loads((ROOT/'verification/refinement_rules.json').read_text(encoding='utf-8'));annotations=json.loads((ROOT/'verification/refinement_annotations.json').read_text(encoding='utf-8'))
  replay=Layer();selected=scope_sources(replay,by,registry)
  for s in selected:refine_source(replay,s,by)
  connect_recordings(replay,by);apply_annotations(replay,by,annotations);make_packets(replay,by,registry)
  for t in SPECS:
   if replay.tables[t]!=new[t]:raise ValueError('Deterministic rule replay mismatch '+t)
 return allby


def runtime():
 return {'python':sys.version,'implementation':sys.implementation.name,'sqlite':sqlite3.sqlite_version,'unicode':unicodedata.unidata_version,'system':platform.system(),'release':platform.release(),'machine':platform.machine()}


def schema_document():
 schema=v2.schema_document();defs=schema['$defs']
 for t in SPECS:
  props={'table':{'const':t},'id':{'type':'string'},**{k:{'const':v} for k,v in VERSIONS.items()}}
  for n,k in columns(t):props[n]={} if k=='JSON' else {'type':['integer' if k=='INTEGER' else 'string','null']}
  if t=='typed_relations_v3':props['relation']={'enum':sorted(RELATIONS)}
  defs[t]={'type':'object','properties':props,'required':list(props),'additionalProperties':False}
 return {'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:trustkernel:refined-ledger:3.0.0','$defs':defs,
         'oneOf':[{'$ref':'#/$defs/'+t} for t in [*base.TABLES,*v2.SPECS,*SPECS]]}


def coverage(layer,by):
 result={'counts':{t:len(v) for t,v in layer.tables.items()},'by_source_type':{},'relation_types':dict(Counter(r['relation'] for r in layer.tables['typed_relations_v3'].values()))}
 for typ in sorted({by['sources_v2'][s['source_id']]['source_type'] for s in layer.tables['scope_v3'].values()}):
  selected={s['source_id'] for s in layer.tables['scope_v3'].values() if by['sources_v2'][s['source_id']]['source_type']==typ}
  before=[c for c in by['candidates_v2'].values() if c['source_id'] in selected];after=[c for c in layer.tables['clauses_v3'].values() if c['source_id'] in selected]
  old_reasons=Counter(f for c in before for f in by['propositions_v2'][c['proposition_id']]['normalization']['unresolved_fields'])
  new_reasons=Counter(f for c in after for f in layer.tables['propositions_v3'][c['proposition_id']]['normalization']['unresolved'])
  result['by_source_type'][typ]={'sources':len(selected),'source_characters':sum(len(by['sources_v2'][s]['text']) for s in selected),'v2_parent_candidates':len(before),
    'v2_kinds':dict(Counter(c['candidate_kind'] for c in before)),'v3_sentence_frames':sum(f['source_id'] in selected and f['frame_kind']=='sentence_frame' for f in layer.tables['frames_v3'].values()),
    'v3_clause_children':len(after),'v3_kinds':dict(Counter(c['kind'] for c in after)),'before_unresolved':dict(old_reasons),'after_unresolved':dict(new_reasons)}
 result['warning']='Parent envelopes and new children have different grains. Changed unresolved labels/counts are not accuracy, recall, truth, or semantic-completeness measures.'
 result['granularity']={'complete_input_copy_appearances':sum(r['relation']=='recorded_input_text_presence' for r in layer.tables['typed_relations_v3'].values()),
                       'copy_appearances_at_calls_without_narrative_output':sum(r['relation']=='recorded_input_text_presence' and r['from_source_id'] is None for r in layer.tables['typed_relations_v3'].values()),
                       'evidence_occurrences_at_calls_without_narrative_output':sum(r['relation']=='recorded_input_evidence_presence' and r['from_source_id'] is None for r in layer.tables['typed_relations_v3'].values())}
 result['per_decision']=[{'run_id':p['run_id'],**{k:p['packet'][k] for k in ('handoff_appearance_occurrences','handoff_unique_endpoint_pairs','direct_final_evidence_occurrences','rationale_character_denominator','matched_literal_characters')},'rationale_clause_children':len(p['packet']['rationale_clause_ids']),'matched_children':len(p['packet']['matched_clause_ids']),'unmatched_children':len(p['packet']['unmatched_clause_ids']),'ancestry_outputs':len(p['packet']['measured_transfer_ancestry'])} for p in layer.tables['packets_v3'].values()]
 return result


def rebuild(rows,path):
 validate(rows,False);old=[r for r in rows if r['table'] not in SPECS];v2.rebuild(old,path)
 with closing(sqlite3.connect(path)) as db:
  db.execute('PRAGMA foreign_keys=ON')
  for t in SPECS:
   defs=['id TEXT PRIMARY KEY',*(k+' TEXT NOT NULL' for k in VERSIONS)]+[n+' '+('TEXT' if k=='JSON' else k) for n,k in columns(t)]
   defs += [f'FOREIGN KEY({n}) REFERENCES {REFS[n]}(id) DEFERRABLE INITIALLY DEFERRED' for n,k in columns(t) if n in REFS]
   db.execute('CREATE TABLE '+t+' ('+','.join(defs)+')')
  with db:
   for t in SPECS:
    names=['id',*VERSIONS,*(n for n,k in columns(t))];j={n for n,k in columns(t) if k=='JSON'}
    db.executemany('INSERT INTO '+t+' VALUES ('+','.join('?' for n in names)+')',[[base.canonical(r[n]) if n in j else r[n] for n in names] for r in rows if r['table']==t])
   db.execute('INSERT INTO ledger_metadata VALUES (?,?)',('refined_sha256',base.sha(''.join(base.canonical(r)+'\n' for r in rows))))
  db.executescript('''CREATE VIEW decision_source_map_v3 AS SELECT d.run_id,d.id decision_source_id,r.id relation_id,r.relation,r.method,r.status,r.from_source_id,r.to_source_id,r.evidence_id,r.witness FROM packets_v3 p JOIN sources_v2 d ON d.id=p.decision_source_id JOIN typed_relations_v3 r ON r.from_source_id=d.id;
CREATE VIEW clause_context_v3 AS SELECT c.*,s.run_id,s.actor,s.source_type,s.stage,s.input_seq,s.output_seq,s.asserted_at,f.section,f.paragraph_start,f.paragraph_end,p.normalization FROM clauses_v3 c JOIN sources_v2 s ON s.id=c.source_id JOIN frames_v3 f ON f.id=c.frame_id JOIN propositions_v3 p ON p.id=c.proposition_id;''')
  if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('V3 SQLite integrity')


def build():
 old,parent_manifest=v2.load_validate();by=group(old)
 registry=json.loads((ROOT/'verification/refinement_rules.json').read_text(encoding='utf-8'));annotations=json.loads((ROOT/'verification/refinement_annotations.json').read_text(encoding='utf-8'))
 layer=Layer();selected=scope_sources(layer,by,registry)
 for s in selected:refine_source(layer,s,by)
 connect_recordings(layer,by);apply_annotations(layer,by,annotations);make_packets(layer,by,registry)
 rows=sorted(old+layer.rows(),key=lambda r:(r['table'],r['id']));validate(rows)
 content=''.join(base.canonical(r)+'\n' for r in rows);DEST.mkdir(parents=True,exist_ok=True)
 (DEST/'ledger.jsonl').write_text(content,encoding='utf-8',newline='\n');rebuild(rows,DEST/'ledger.sqlite')
 paths=['refined.py','refine_rules.py','refined_query.py','refinement_rules.json','refinement_annotations.json','REFINEMENT_CONTRACT.md','tests/test_refined.py']
 hashes={'verification/'+p:base.sha((ROOT/'verification'/p).read_bytes()) for p in paths if (ROOT/'verification'/p).exists()}
 environment=runtime();build_id='refined-v3-'+base.sha(base.canonical({'data':base.sha(content),'parent':parent_manifest['canonical_sha256'],'implementation':hashes,'runtime':environment}))[:20]
 cov=coverage(layer,by);cov.update(build_id=build_id,canonical_sha256=base.sha(content),parent_build_id=parent_manifest['build_id'])
 ctext=json.dumps(cov,indent=2,ensure_ascii=False)+'\n';(DEST/'coverage.json').write_text(ctext,encoding='utf-8',newline='\n')
 preservation={p:base.sha((ROOT/'verification'/p).read_bytes()) for p in ('data/full/ledger.jsonl','data/pilot/ledger.jsonl','data/expanded-v2/ledger.jsonl','releases/TrustKernel-Atomic-Ledger-Draft-v1.1.zip','releases/TrustKernel-Expanded-Candidate-Ledger-v2.zip')}
 m={'build_id':build_id,'versions':VERSIONS,'canonical_sha256':base.sha(content),'coverage_sha256':base.sha(ctext),'parent_build_id':parent_manifest['build_id'],'parent_canonical_sha256':parent_manifest['canonical_sha256'],'rows':len(rows),'new_counts':cov['counts'],'implementation_hashes':hashes,'runtime':environment,'historical_hashes':preservation,'external_inference_calls':0,'accepted_support_claims':0}
 packets_text=json.dumps({'build_id':build_id,'packets':[p['packet'] for p in layer.tables['packets_v3'].values()]},indent=2,ensure_ascii=False)+'\n'
 m['decision_packets_sha256']=base.sha(packets_text)
 (DEST/'decision-packets.json').write_text(packets_text,encoding='utf-8',newline='\n')
 (DEST/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8',newline='\n')
 (ROOT/'verification/refined-schema.json').write_text(json.dumps(schema_document(),indent=2)+'\n',encoding='utf-8',newline='\n')
 lines=['# V3 provisional refinement build','',f'Build ID: `{build_id}`','',f'Canonical SHA-256: `{base.sha(content)}`','',f'Accepted parent: `{parent_manifest["build_id"]}`','',
        '| New table | Rows |','|---|---:|']+[f'| {t} | {n} |' for t,n in cov['counts'].items()]
 lines+=['','Rules/annotations/runtime hashes are bound in manifest.json. Clauses are source-scoped provisional interpretations, not verified truth.','']
 (DEST/'BUILD.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
 return cov


def validate_index(rows,path):
 by=group(rows)
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
  if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('V3 index integrity')
  digest=base.sha(''.join(base.canonical(r)+'\n' for r in rows))
  if db.execute("SELECT value FROM ledger_metadata WHERE key='refined_sha256'").fetchone()!=(digest,):raise ValueError('Index build mismatch')
  for t,spec in {**base.TABLES,**v2.SPECS,**SPECS}.items():
   parts=spec.split();cols=list(zip(parts[::2],parts[1::2]));names=['id','schema_version','normalization_version','extraction_version',*(n for n,k in cols)];j={n for n,k in cols if k=='JSON'}
   expected=[tuple(base.canonical(r[n]) if n in j else r[n] for n in names) for _,r in sorted(by[t].items())]
   if db.execute('SELECT '+','.join(names)+' FROM '+t+' ORDER BY id').fetchall()!=expected:raise ValueError('Index rows mismatch '+t)


def load_validate():
 data=(DEST/'ledger.jsonl').read_bytes();rows=[json.loads(l) for l in data.decode('utf-8').splitlines()];m=json.loads((DEST/'manifest.json').read_text(encoding='utf-8'))
 if base.sha(data)!=m['canonical_sha256'] or base.sha((DEST/'coverage.json').read_bytes())!=m['coverage_sha256'] or base.sha((DEST/'decision-packets.json').read_bytes())!=m['decision_packets_sha256']:raise ValueError('V3 bundle hash mismatch')
 for p,h in m['implementation_hashes'].items():
  if base.sha((ROOT/p).read_bytes())!=h:raise ValueError('V3 implementation changed '+p)
 for p,h in m['historical_hashes'].items():
  if base.sha((ROOT/'verification'/p).read_bytes())!=h:raise ValueError('Historical release changed '+p)
 by=validate(rows);validate_index(rows,DEST/'ledger.sqlite')
 return rows,m


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','validate','rebuild']);a=p.parse_args()
 if a.command=='build':
  c=build();print(json.dumps({'build_id':c['build_id'],'counts':c['counts'],'relations':c['relation_types'],'decisions':c['per_decision']},indent=2))
 elif a.command=='validate':
  r,m=load_validate();print(m['build_id']+' PASS '+str(len(r))+' rows')
 else:
  rows=[json.loads(l) for l in (DEST/'ledger.jsonl').read_text(encoding='utf-8').splitlines()];rebuild(rows,DEST/'ledger.sqlite');print('V3 rebuild PASS')


if __name__=='__main__':main()
