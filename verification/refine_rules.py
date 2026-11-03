"""V3 provisional surface refinement; exact spans and conservative scope guards."""
import re
from . import processing as v2

VERSION='3.0.1'
LABEL=re.compile(r'^\*\*(?P<label>[^*:\n]{1,80})(?::\*\*|\*\*:)\s*')
SCALAR_SECTIONS={'rating','recommendation','action','price target','time horizon','entry price','stop loss','final transaction proposal'}
DISCOURSE=re.compile(r"^(?:Let me\b|I(?:'ll| will) (?:separate|outline|summarize|explain)\b|To (?:summarize|organize|be clear)\b)",re.I)
POSITION=re.compile(r'^(?:I|we)\s+(?:support|recommend|agree|would|favor)\b',re.I)
VERBS=v2.VERBS+r'|wins?|reflects?|warrants?|leaves?|rejects?|retains?|authorizes?|coexist(?:s)?|argues?|warns?|says?|states?|notes?|captures?|separates?|exceeds?|breaches?|complies|fits|establish(?:es)?'
FINITE=re.compile(r'\b(?:'+VERBS+r')\b',re.I)
CONDITION=re.compile(r'\b(?:only if|only after|only when|if|unless|when|subject to|provided that|assuming)\b',re.I)
ATTRIBUTION=re.compile(r'\b(?:according to|says?|said|notes?|argues?|claims?|alleges?|warns?|warning|persuasive|correctly)\b',re.I)
BECAUSE=re.compile(r'\b(?P<neg>not\s+)?because\b',re.I)
COORDINATOR=re.compile(r';|\s+(?:and|but|while|whereas|yet|or)\s+',re.I)
IMPERATIVE=re.compile(r'^(?:do not\s+|don.t\s+)?(?:maintain|hold|reduce|consider|seek|review|assess|validate|preserve|reassess|check|treat|wait|confirm|obtain|use|make|initiate|remain|add|reconsider|authorize|avoid)\b',re.I)


def trim(text,a,b):
 while a<b and text[a].isspace():a+=1
 while b>a and text[b-1].isspace():b-=1
 return a,b


def frames(text):
 """Lossless sentence-frame/section/whitespace partition; metadata never a predicate."""
 result=[];base=0;section='unlabeled'
 for line in text.splitlines(keepends=True):
  begin=0;m=LABEL.match(line)
  transaction=re.match(r'^FINAL TRANSACTION PROPOSAL:\s*',line)
  if not m and transaction:
   section='FINAL TRANSACTION PROPOSAL';result.append((base,base+transaction.end(),'section_metadata',section));begin=transaction.end()
  if m:
   section=m['label'];result.append((base,base+m.end(),'section_metadata',section));begin=m.end()
  cuts=[begin]
  for p in re.finditer(r'[.!?](?=\s|$)',line[begin:]):
   end=begin+p.end();tokens=line[begin:end].split();token=tokens[-1].lower() if tokens else ''
   if token in v2.ABBREVIATIONS or re.search(r'\b[A-Za-z]\.$',token):continue
   cuts.append(end)
  cuts.append(len(line))
  for a,b in zip(cuts,cuts[1:]):
   if a==b:continue
   l,r=trim(line,a,b)
   if a<l:result.append((base+a,base+l,'whitespace',section))
   if l<r:result.append((base+l,base+r,'sentence_frame',section))
   if r<b:result.append((base+r,base+b,'whitespace',section))
  base+=len(line)
 return result


def slot(text,a,b):
 a,b=trim(text,a,b)
 while b>a and text[b-1] in '.,;:!?*`':b-=1
 while a<b and text[a] in '*`':a+=1
 return dict(text=text[a:b],start=a,end=b) if a<b and re.search(r'\w',text[a:b]) else None


def parse_slots(text,a,b):
 body=text[a:b]
 m=re.match(r'^(?:[-*+]\s+|\d+[.)]\s+)?(?P<subject>[A-Za-z][^.!?;:]{0,160}?)\s+(?P<predicate>'+VERBS+r')\b\s*(?P<value>.*)$',body,re.I)
 if not m:
  imperative=re.match(r"^(?:(?:do not|don't)\s+)?(?P<predicate>maintain|hold|reduce|consider|seek|review|assess|validate|preserve|reassess|check|treat|wait|confirm|obtain|use|make|initiate|remain|add|reconsider|authorize|avoid)\b\s*(?P<value>.*)$",body,re.I)
  if imperative:
   f={'subject':None,**{key:slot(text,a+imperative.start(key),a+imperative.end(key)) for key in ('predicate','value')}}
   return f,['subject_implicit_addressee_not_inferred']+(['empty_or_punctuation_only_complement'] if f['value'] is None else [])
  return {'subject':None,'predicate':None,'value':None},['subject','predicate','value','unsupported_predication']
 fields={key:slot(text,a+m.start(key),a+m.end(key)) for key in ('subject','predicate','value')}
 unresolved=[k for k,v in fields.items() if v is None]
 if fields['subject'] and re.search(r'\b(?:it|they|this|that|those|these|he|she|we|I)\b',fields['subject']['text'],re.I):unresolved.append('subject_coreference')
 if fields['value'] is None:unresolved.append('empty_or_punctuation_only_complement')
 return fields,unresolved


def viable(text,a,b):
 a,b=trim(text,a,b)
 # A predicate before a colon/list is not proof that a truncated noun-list half
 # is an independent clause. Keep this grammar deliberately small.
 body=text[a:b].rstrip(', ')
 if ':' in body or ',' in body or COORDINATOR.search(body):return False
 f,u=parse_slots(text,a,b)
 return (bool(f['subject'] and f['predicate']) and len(list(FINITE.finditer(body)))==1) or bool(IMPERATIVE.match(body))


def decompose(text,left,right):
 """Return exact children with roles, matched rules, connectors and explicit guards."""
 a,b=trim(text,left,right);body=text[a:b]
 if DISCOURSE.match(body):return [dict(start=a,end=b,role='discourse',rule='R030',connector=None,condition_spans=[],extra=['embedded_assertions_not_exhaustively_parsed'])]
 # Fence attachment before reason/condition parsing, irrespective of whether
 # either branch fits the narrow predication grammar. Failure to parse a
 # contextual comma/list branch must never enable a later IF to govern it.
 if ';' in body:return semicolon_children(text,a,b)
 reasons=list(BECAUSE.finditer(body))
 if reasons:
  result=[];head_end=a+reasons[0].start();ha,hb=trim(text,a,head_end)
  while hb>ha and text[hb-1] in ',—–- ':hb-=1
  if ha<hb:result.append(dict(start=ha,end=hb,role='reason_conclusion',rule='R040',connector=None,condition_spans=[],extra=[]))
  for i,m in enumerate(reasons):
   ca=a+m.end();cb=a+reasons[i+1].start() if i+1<len(reasons) else b
   ca,cb=trim(text,ca,cb)
   tail=re.search(r'(?:[,—–-]\s*|\bbut\s*)$',text[ca:cb],re.I)
   if tail:cb=ca+tail.start();ca,cb=trim(text,ca,cb)
   if ca>=cb:continue
   before=body[max(0,m.start()-16):m.start()]
   uncertain_negation=not m['neg'] and bool(re.search(r'\bnot\s+(?:only|just|merely)\s*$',before,re.I))
   role='rejected_reason' if m['neg'] else 'reason_polarity_unresolved' if uncertain_negation else 'declared_reason'
   result.append(dict(start=ca,end=cb,role=role,rule='R040',connector=dict(text=m.group(),start=a+m.start(),end=a+m.end()),condition_spans=[],extra=['reason_is_author_declared_not_validated_cause']+(['reason_negation_scope'] if uncertain_negation else [])))
  return result
 if CONDITION.search(body):return condition_children(text,a,b)
 # Independent explicit subjects may be split; noun lists/shared subjects may not.
 for m in COORDINATOR.finditer(body):
  x,y=trim(text,a,a+m.start());z,w=trim(text,a+m.end(),b)
  if viable(text,x,y) and viable(text,z,w):
   connector=dict(text=m.group(),start=a+m.start(),end=a+m.end())
   role='alternative_clause' if m.group().strip().lower()=='or' else 'coordinated_clause'
   return [dict(start=u,end=v,role=role,rule='R060',connector=connector,condition_spans=[],extra=['coordination_semantics_not_inferred']) for u,v in [(x,y),(z,w)]]
 extra=['coordination_or_shared_scope_unresolved'] if COORDINATOR.search(body) else []
 return [dict(start=a,end=b,role='author_position' if POSITION.match(body) else 'statement_candidate',rule='R070' if not extra else 'R090',connector=None,condition_spans=[],extra=extra)]


def semicolon_children(text,a,b):
 result=[];cursor=a
 for boundary in [m.start()+a for m in re.finditer(';',text[a:b])]+[b]:
  left,right=trim(text,cursor,boundary);cursor=boundary+1
  if left>=right:continue
  for child in decompose(text,left,right):
   child['attachment_span']={'start':left,'end':right}
   child['boundary_rule']='R035'
   child['extra']+=['semicolon_branch_local_attachment_only','cross_branch_scope_unresolved']
   result.append(child)
 return result


def condition_children(text,a,b):
 body=text[a:b];markers=list(CONDITION.finditer(body));extra=[]
 if ';' in body:return semicolon_children(text,a,b)
 if len(markers)>1:extra.append('nested_or_alternative_condition_logic_unresolved')
 if re.search(r'\bor\s+(?:only\s+)?if\b',body,re.I):extra.append('alternative_condition_markers_preserved')
 prefix=re.match(r'^(?:If|Unless|When)\s+(?P<condition>.+?),\s*(?P<outcome>.+)$',body,re.I)
 if prefix:
  ca,cb=a+prefix.start('condition'),a+prefix.end('condition');oa,ob=a+prefix.start('outcome'),b
  guard=dict(text=text[ca:cb],start=ca,end=cb,marker=dict(text=markers[0].group(),start=a+markers[0].start(),end=a+markers[0].end()))
  return [dict(start=ca,end=cb,role='condition_antecedent',rule='R050',connector=None,condition_spans=[guard],extra=extra+['antecedent_not_asserted_true']),
          dict(start=oa,end=ob,role='conditional_outcome',rule='R050',connector=None,condition_spans=[guard],extra=extra+['condition_required_not_unconditional_fact'])]
 suffix=re.match(r'^(?P<outcome>.+?)\s+(?P<marker>only if|only after|only when|if|unless|when|subject to|provided that)\s+(?P<condition>.+)$',body,re.I)
 if suffix and len(markers)==1:
  # A new IF-clause after a colon, or an IF...comma...instruction, is not the
  # supported postposed-condition grammar. Withhold a typed attachment.
  if ':' in suffix['outcome'] or re.search(r",\s*(?:then\s+)?(?:do not|don't|maintain|hold|reduce|consider|remain|add|initiate|reassess|reconsider)\b",suffix['condition'],re.I):
   return [dict(start=a,end=b,role='conditional_envelope',rule='R050',connector=None,condition_spans=[],extra=extra+['postposed_condition_clause_boundary_unresolved'])]
  ca,cb=a+suffix.start('condition'),b;oa,ob=a+suffix.start('outcome'),a+suffix.end('outcome')
  guard=dict(text=text[ca:cb],start=ca,end=cb,marker=dict(text=suffix['marker'],start=a+suffix.start('marker'),end=a+suffix.end('marker')))
  return [dict(start=oa,end=ob,role='conditional_outcome',rule='R050',connector=None,condition_spans=[guard],extra=['condition_required_not_unconditional_fact']),
          dict(start=ca,end=cb,role='condition_antecedent',rule='R050',connector=None,condition_spans=[guard],extra=['antecedent_not_asserted_true'])]
 return [dict(start=a,end=b,role='conditional_envelope',rule='R050',connector=None,condition_spans=[],extra=extra+['condition_attachment_unresolved'])]


def condition_attachment_issues(text,child,frame_start,frame_end):
 """Structural attachment invariant; full-frame inherited cues are not edges."""
 boundary=child.get('attachment_span',{'start':frame_start,'end':frame_end});issues=[]
 for guard in child['condition_spans']:
  marker=guard['marker']
  lo=min(child['start'],guard['start'],marker['start']);hi=max(child['end'],guard['end'],marker['end'])
  if ';' in text[lo:hi]:issues.append('typed_condition_crosses_semicolon')
  if not boundary['start']<=lo<hi<=boundary['end']:issues.append('typed_condition_outside_attachment_branch')
 return sorted(set(issues))


def normalization(text,child,frame_start,frame_end,paragraph_start,paragraph_end):
 a,b=child['start'],child['end'];body=text[a:b];context=text[frame_start:frame_end]
 local={name:v2.cues(pattern,body,a) for name,pattern in [('negation',v2.NEGATION),('modality',v2.MODAL),('uncertainty',v2.UNCERTAINTY),('conditions',CONDITION),('attribution',ATTRIBUTION),('time',v2.TIME)]}
 inherited={name:v2.cues(pattern,context,frame_start) for name,pattern in [('negation',v2.NEGATION),('modality',v2.MODAL),('uncertainty',v2.UNCERTAINTY),('conditions',CONDITION),('attribution',ATTRIBUTION)]}
 attachment=child.get('attachment_span',{'start':frame_start,'end':frame_end})
 branch_conditions=v2.cues(CONDITION,text[attachment['start']:attachment['end']],attachment['start'])
 unresolved=list(child['extra'])
 if COORDINATOR.search(body) and child['role'] not in ('coordinated_clause','alternative_clause','scalar_declaration'):
  unresolved.append('within_component_coordination_unresolved')
 if child['role']=='scalar_declaration':fields={'subject':None,'predicate':None,'value':slot(text,a,b)};unresolved+=['semantic_subject_predicate_not_inferred_from_section']
 elif child['role']=='discourse':fields={'subject':None,'predicate':None,'value':None};unresolved+=['discourse_not_market_fact']
 elif 'coordination_or_shared_scope_unresolved' in unresolved:
  fields={'subject':None,'predicate':None,'value':None};unresolved+=['subject','predicate','value']
 else:fields,unknown=parse_slots(text,a,b);unresolved+=unknown
 if not local['time']:unresolved.append('valid_time_unresolved')
 if inherited['negation']:unresolved.append('negation_scope_retained_not_resolved')
 if inherited['modality']:unresolved.append('modality_scope_retained_not_resolved')
 if inherited['attribution']:unresolved.append('attribution_scope_retained_not_resolved')
 if branch_conditions or child['condition_spans']:unresolved.append('conditional_scope_guard_retained')
 elif inherited['conditions']:unresolved.append('other_branch_condition_context_unassigned')
 if len(branch_conditions)>1:unresolved.append('nested_condition_boolean_scope_unresolved')
 elif len(inherited['conditions'])>len(branch_conditions):unresolved.append('other_frame_condition_markers_not_locally_assigned')
 if re.search(r'\$|\bUSD\b|%',body):unresolved.append('unit_value_attachment_unresolved')
 if child['role']=='scalar_declaration':kind='scalar_report_declaration'
 elif child['role'] in ('declared_reason','rejected_reason','reason_polarity_unresolved','reason_conclusion'):
  kind='author_rationale_component'
 elif child['role']=='discourse':kind='discourse'
 elif child['role'] in ('condition_antecedent','conditional_outcome','conditional_envelope'):kind='conditional_component'
 elif child['role']=='author_position' or POSITION.match(body):kind='author_position'
 elif IMPERATIVE.match(body):kind='recommendation_candidate'
 elif inherited['attribution']:kind='attributed_statement_candidate'
 elif all(fields.values()) and not child['extra']:kind='predication_candidate'
 else:kind='unresolved_fragment'
 return dict(**fields,kind=kind,role=child['role'],local_cues=local,inherited_frame_cues=inherited,
             condition_spans=child['condition_spans'],connector=child['connector'],
             scope={'frame_start':frame_start,'frame_end':frame_end,'paragraph_start':paragraph_start,'paragraph_end':paragraph_end,
                    'attachment_start':attachment['start'],'attachment_end':attachment['end'],'typed_condition_attachment_crosses_semicolon':False,
                    'paragraph_cues_are_context_not_automatic_clause_conditions':True},
             slot_rule='R010' if child['role']=='scalar_declaration' else 'R075' if fields['subject'] is None and fields['predicate'] and IMPERATIVE.match(body) else 'R070',
             unresolved=sorted(set(unresolved)),accepted_factual_support=False,semantic_identity='unmerged_source_occurrence')
