"""Reusable, lossless surface-rule processing. No truth or semantic-recall claims."""
import re

VERSION='2.0.0'
VERBS=r'is|are|was|were|be|been|has|have|had|does|do|did|can|cannot|could|may|might|would|should|must|will|shows?|requires?|supports?|means?|offers?|creates?|depends?|returned|returns?|repeats?|remains?|rose|fell|closes?|opened|reached|contains?|provides?|establish(?:es)?|justif(?:y|ies)|preserves?|lacks?|reduces?|increases?|makes?|made|suggests?|represents?|reflects?|count(?:s)?|confirm(?:s)?|supplies|supplied|alleges|alleged'
FINITE=re.compile(r'\b(?:'+VERBS+r')\b',re.I)
CONDITION=re.compile(r'\b(?:if|unless|provided that|only after|only when|subject to|assuming)\b',re.I)
MODAL=re.compile(r'\b(?:may|might|could|would|should|must|can|cannot|will)\b',re.I)
NEGATION=re.compile(r"\b(?:not|no|never|cannot|can't|without|neither|lacks?|insufficient)\b",re.I)
UNCERTAINTY=re.compile(r'\b(?:unverified|alleged|allegation|uncertain|unknown|possible|potential|plausible|hypothetical|tentative|unconfirmed|inconclusive|unavailable|unsupported)\b',re.I)
REASON=re.compile(r'\b(?:because|therefore|given|as a result|so that)\b',re.I)
ASSUMPTION=re.compile(r'\b(?:assume|assuming|assumption|provided that|subject to)\b',re.I)
IMPERATIVE=re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*)?(?:avoid|obtain|verify|keep|maintain|hold|reduce|consider|seek|review|assess|do not|don't|require|validate|preserve|reassess|check|look|treat|wait|confirm|request|compare|use)\b",re.I)
NUMBER=re.compile(r'\b\d{4}-\d{2}-\d{2}\b|(?:\$\s*)?\b\d[\d,]*(?:\.\d+)?(?:\s*(?:%|USD|days?|hours?|x))?',re.I)
TIME=re.compile(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:[–-]\d{1,2})?(?:,?\s+\d{4})?|\b(?:today|current|next|recent|latest|past|long.term|short.term|medium.term)\b',re.I)
ABBREVIATIONS={'e.g.','i.e.','mr.','mrs.','dr.','vs.','etc.'}


def cues(pattern,text,start):
    return [dict(text=m.group(),start=start+m.start(),end=start+m.end()) for m in pattern.finditer(text)]


def paragraph_bounds(text,left,right):
    before=text.rfind('\n\n',0,left)
    after=text.find('\n\n',right)
    return (0 if before<0 else before+2,len(text) if after<0 else after)


def segments(text):
    """Partition every code point, including whitespace; never synthesize text."""
    spans=[];offset=0;heading=''
    for line in text.splitlines(keepends=True):
        stripped=line.strip()
        if stripped.startswith('#'):heading=stripped
        cuts=[0]
        # Keep condition-bearing lines whole to avoid dropping antecedent scope.
        if not CONDITION.search(line) and not ('|' in line):
            for m in re.finditer(r'[.!?;](?=\s|$)',line):
                token=line[:m.end()].split()[-1].lower() if line[:m.end()].split() else ''
                if token in ABBREVIATIONS or re.search(r'\b[A-Za-z]\.$',token):continue
                # An ordered list marker is formatting, not a sentence boundary.
                if re.fullmatch(r'\s*\d+\.',line[:m.end()]):continue
                cuts.append(m.end())
        cuts.append(len(line))
        for a,b in zip(cuts,cuts[1:]):
            if a==b:continue
            chunk=line[a:b];l=len(chunk)-len(chunk.lstrip());r=len(chunk.rstrip())
            if l:spans.append((offset+a,offset+a+l,heading))
            if r>l:spans.append((offset+a+l,offset+a+r,heading))
            if len(chunk)>max(l,r):spans.append((offset+a+max(l,r),offset+b,heading))
        offset+=len(line)
    return spans


def classify(text,heading=''):
    tags=[]
    if not text.strip() or re.fullmatch(r'[\s|:#*`_\-–]+',text):
        return 'background_structural_material',['formatting_or_whitespace'],'formatting_v2'
    conditional=bool(CONDITION.search(text));modal=bool(MODAL.search(text));imperative=bool(IMPERATIVE.search(text))
    if conditional:tags.append('condition_present_scope_unresolved')
    if modal:tags.append('modality_present')
    if imperative:tags.append('guidance_candidate')
    if NEGATION.search(text):tags.append('negation_present_scope_unresolved')
    if UNCERTAINTY.search(text):tags.append('uncertainty_or_missingness_present')
    if REASON.search(text):tags.append('explicit_reason_wording')
    if ASSUMPTION.search(text):tags.append('explicit_assumption_wording')
    if re.search(r'\b(?:and|but|while|whereas|although|nor|neither)\b|;',text,re.I):tags.append('possible_compound_statement')
    if re.search(r'indicator|framework|mechanism|general|background|ecosystem|thesis',heading,re.I):tags.append('background_context_candidate')
    if text.rstrip('*` ').endswith('?'):
        return 'question',tags+['question_premises_not_exhaustively_extracted'],'question_surface_v2'
    if conditional or imperative or re.search(r'\b(?:may|might|could|would|should|must)\b',text,re.I):
        return 'conditional_guidance_hypothesis',tags,'condition_modal_guidance_v2'
    if FINITE.search(text):return 'candidate_assertion',tags,'finite_verb_candidate_v2'
    if text.count('|')>=2:
        return 'candidate_assertion',tags+['table_record_alignment_unresolved'],'table_record_candidate_v2'
    if re.match(r'^\*{0,2}[A-Za-z][^:\n]{0,90}\*{0,2}:\s*\S',text):
        return 'candidate_assertion',tags+['structured_field_candidate'],'label_value_candidate_v2'
    if text.startswith('#') or re.fullmatch(r'\*{2}[^*]+\*{2}:?',text) or re.fullmatch(r'\d+[.)]',text):
        return 'background_structural_material',tags+['nonassertive_label_candidate'],'heading_label_v2'
    return 'unresolved_interpretation',tags+['substantive_fragment_or_unrecognized_statement'],'unresolved_surface_v2'


def normalize(text,start,disposition,tags):
    """Conservative surface slots; unresolved scope is first-class data."""
    neg=cues(NEGATION,text,start);mod=cues(MODAL,text,start);conditions=cues(CONDITION,text,start)
    uncertainty=cues(UNCERTAINTY,text,start);numbers=cues(NUMBER,text,start);times=cues(TIME,text,start)
    subject=predicate=value=None
    unresolved=[]
    # Do not remove an if-clause or split a compound into an unconditional fact.
    if conditions or 'possible_compound_statement' in tags:
        unresolved+=['atomicity','condition_or_coordination_scope','subject','predicate','value']
    else:
        label=re.match(r'^(?P<label>\*{0,2}[A-Za-z][^:\n]{0,90}?\*{0,2}):\s*(?P<value>.+)$',text)
        svo=re.match(r'^(?:[-*+]\s+|\d+[.)]\s+)?(?P<subject>[A-Za-z][^.!?;:]{0,160}?)\s+(?P<predicate>'+VERBS+r')\b\s*(?P<value>.*)$',text,re.I)
        match=label or svo
        if match:
            def slot(name):
                a,b=match.span(name)
                return dict(text=text[a:b],start=start+a,end=start+b)
            if label:predicate=slot('label');value=slot('value');unresolved.append('subject')
            else:subject=slot('subject');predicate=slot('predicate');value=slot('value')
        else:unresolved+=['subject','predicate','value']
    if neg:unresolved.append('negation_scope')
    if mod:unresolved.append('modality_scope')
    if not times:unresolved.append('asserted_valid_time')
    if len(numbers)>1:unresolved.append('numeric_role_alignment')
    if 'table_record_alignment_unresolved' in tags:unresolved+=['table_column_alignment','atomicity']
    if disposition=='unresolved_interpretation':unresolved.append('statement_interpretation')
    units=[dict(text=m.group(),start=start+m.start(),end=start+m.end()) for m in re.finditer(r'\$|\bUSD\b|%|\b(?:days?|hours?)\b',text,re.I)]
    if 'atomicity' in unresolved:atomization='compound_or_scope_unresolved'
    elif subject and predicate and value and value['text'] and len(list(FINITE.finditer(text)))==1:atomization='surface_single_predication_candidate'
    elif predicate and value and 'structured_field_candidate' in tags:atomization='surface_structured_field_candidate'
    else:atomization='statement_envelope_not_certified_atomic'
    return dict(subject=subject,predicate=predicate,value=value,numeric_expressions=numbers,units=units,time_expressions=times,
                negation=neg,modality=mod,conditions=conditions,uncertainty=uncertainty,
                unresolved_fields=sorted(set(unresolved)),identity_status='unmerged_source_scoped_candidate',
                atomization_status=atomization)


def explicit_numeric_fields(text,start):
    """Child candidates only for an explicit field/number pairing, never inferred OHLC."""
    pattern=re.compile(r'\b(?P<field>open|high|low|close|volume)\s+(?:of\s+|at\s+|was\s+|=\s*)?(?:\*\*)?\$?(?P<number>\d[\d,]*(?:\.\d+)?)(?:\*\*)?',re.I)
    for m in pattern.finditer(text):
        yield dict(start=start+m.start(),end=start+m.end(),predicate=dict(text=m['field'],start=start+m.start('field'),end=start+m.end('field')),
                   value=dict(text=m['number'],start=start+m.start('number'),end=start+m.end('number')))
