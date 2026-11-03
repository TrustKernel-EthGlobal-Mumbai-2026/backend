"""Scoped offline verifier against procedural-loop-contract-0.1.

Internal primitives use ordinary values, not a competing packet format.
No I/O, network, model calls, source mutation or host-state changes.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import copy

from procedural_loop import contracts as c


VERIFIER_VERSION='procedural-verifier-0.1'
REQUIRED_CAPABILITIES={'evidence_timestamps','source_versions','source_text',
                       'declared_dependencies','observed_prefix'}
LIMITS=[
    'Authored synthetic quote procedure only; no market truth, Hold suitability or trade authority.',
    'Content/prefix capture is declared within fixture scope, not private attention or hidden dependency completeness.',
    'Local deterministic clearance binding is not a cryptographic authorization or publisher-authenticity proof.',
    'Only delivered packet evidence is assessed; fixture schedule, refresh/ack and host enforcement are not invented here.',
]
_QUOTE=re.compile(r'Synthetic ETH-USD quote: (?P<amount>[+-]?(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?) USD at (?P<instant>\S+)\. Authored test data\.')


class MissingPrerequisite(ValueError):
    """Required information is absent/unknown; assessment must remain inconclusive."""


class InvalidBinding(ValueError):
    """Provided data is malformed or has an invalid declared binding."""


def _utc(value):
    if value is None:
        raise MissingPrerequisite('timestamp_missing')
    if not isinstance(value,str) or not value:
        raise InvalidBinding('timestamp_invalid')
    try:
        parsed=c.parse_time(value)
    except ValueError as exc:
        raise InvalidBinding('timestamp_invalid') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidBinding('timestamp_timezone_missing')
    return parsed.astimezone(timezone.utc)


def _scalar(value):
    if value is None:
        raise MissingPrerequisite('scalar_missing')
    if not isinstance(value,str) or not re.fullmatch(r'[+-]?(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?',value):
        raise InvalidBinding('scalar_invalid')
    return Decimal(value.replace(',',''))


def _expiry(valid_at, max_age_seconds, valid_until=None):
    begin=_utc(valid_at)
    if max_age_seconds is None:
        raise MissingPrerequisite('max_age_missing')
    if isinstance(max_age_seconds,bool) or not isinstance(max_age_seconds,(int,float)) or not 0<=max_age_seconds<float('inf'):
        raise InvalidBinding('max_age_invalid')
    try:
        end=begin+timedelta(seconds=max_age_seconds)
    except OverflowError as exc:
        raise InvalidBinding('max_age_overflow') from exc
    if valid_until is not None:
        declared=_utc(valid_until)
        if declared<=begin:
            raise InvalidBinding('valid_interval_invalid')
        end=min(end,declared)
    return begin,end


def _anchor(evidence, extract=None):
    result={k:copy.deepcopy(evidence[k]) for k in ('id','source_id','source_version','content_digest','pointer',
                'valid_at','retrieved_at','recorded_at','run_id','actor_id','call_id','causal_refs')}
    if extract is not None:
        result['extract']={k:copy.deepcopy(extract[k]) for k in ('id','span','quote','field','value','unit','source_version')}
    return result


def _is_visible(evidence,as_of,context_time):
    """Unknown/future clock rows never become known supersession witnesses."""
    values=[_utc(evidence[k]) for k in ('valid_at','retrieved_at','recorded_at')]
    valid,retrieved,recorded=values
    return valid<=retrieved<=recorded<=context_time<=as_of


def _finish(packet,binding,findings):
    statuses=[f['status'] for f in findings if f['required']]
    status=next((s for s in ('ERROR','FAIL','INCONCLUSIVE','NOT_APPLICABLE') if s in statuses),'PASS')
    if not statuses:
        status='INCONCLUSIVE'
    blocked=[f for f in findings if f['required'] and f['status']!='PASS']
    codes=sorted({f['reason_code'] for f in blocked})
    ids=sorted({f['subject'].get('evidence_id') for f in blocked if f['subject'].get('evidence_id')})
    if status=='PASS':
        action='none'
    elif status=='ERROR':
        action='repair_invalid_packet_and_resubmit'
    elif any('CAPTURE' in code or 'DEPENDENC' in code or 'MISSING' in code for code in codes) and status=='INCONCLUSIVE':
        action='supply_missing_prerequisites_and_resubmit'
    else:
        action='refresh_evidence_and_resubmit'
    packet_id=packet.get('packet_id') if isinstance(packet,dict) else None
    if type(packet_id) is not str:
        packet_id=None
    else:
        try:packet_id.encode('utf-8')
        except UnicodeError:packet_id=None
    output={'schema_version':c.SCHEMA_VERSION,'verifier_version':VERIFIER_VERSION,
        'packet_id':packet_id,
        'status':status,'findings':findings,'required_response':{'action':action,'blocking_codes':codes,
            'evidence_ids':ids,'host_response_not_executed_by_verifier':True},
        'binding':binding,'limits':list(LIMITS)}
    output['assessment_id']='assessment:'+c.digest(output)
    output['clearance']=None
    if status=='PASS' and binding is not None and all(f['status']=='PASS' for f in findings if f['required']):
        clearance={'schema_version':c.SCHEMA_VERSION,'verifier_version':VERIFIER_VERSION,
            'assessment_id':output['assessment_id'],'binding':copy.deepcopy(binding),'status':'PASS',
            'required_finding_ids':[f['finding_id'] for f in findings if f['required']],
            'scope':'authored_fixture_quote_procedure_only'}
        clearance['clearance_id']='clearance:'+c.digest(clearance)
        output['clearance']=clearance
    return output


def assess(packet):
    """Pure dict->dict assessment; never performs a refresh, host hold or writes.

    Invalid packet shape/digests give ERROR. Missing prerequisites remain
    INCONCLUSIVE. Only the narrow authored observed_quote mapping is executable.
    """
    findings=[]
    try:
        issues=c.validate_packet(packet)
    except (ValueError,TypeError,KeyError,OverflowError,UnicodeError,RecursionError) as exc:
        issues=[{'path':'/','code':'INVALID_PACKET','message':str(exc)}]
    if issues:
        finding={'obligation':'packet_binding','method_version':VERIFIER_VERSION,
            'required':True,'status':'ERROR','reason_code':'INVALID_PACKET_BINDING',
            'subject':{},'expected':'shared contract and content identities valid','observed':issues,
            'positive_witnesses':[],'negative_witnesses':[],
            'mapping_status':'contract_mechanical','as_of':None,'context':None,'limits':list(LIMITS)}
        finding['finding_id']='finding:'+c.digest(finding)
        return _finish(packet,None,[finding])
    # Detach input to ensure output aliases cannot mutate source/assessment data.
    packet=copy.deepcopy(packet)
    binding=c.clearance_binding(packet)
    proposal,policy,context=packet['proposal'],packet['policy'],packet['context']

    def emit(obligation,status,reason,expected,observed,evidence=None,extract=None,positive=None,negative=None):
        subject={'proposal_id':proposal['id'],'proposal_revision':proposal['revision']}
        if evidence:subject['evidence_id']=evidence['id']
        if extract:subject['extract_id']=extract['id']
        finding={'obligation':obligation,'method_version':VERIFIER_VERSION,'required':True,
            'status':status,'reason_code':reason,'subject':subject,
            'expected':expected,'observed':observed,'as_of':proposal['as_of'],
            'context':{'id':context['id'],'revision':context['revision'],'observed_at':context['observed_at']},
            'mapping_status':'fixture_authored_explicit_rule_not_blanket_semantic_support',
            'positive_witnesses':positive if positive is not None else ([_anchor(evidence,extract)] if evidence and status=='PASS' else []),
            'negative_witnesses':negative if negative is not None else ([_anchor(evidence,extract)] if evidence and status=='FAIL' else []),
            'limits':list(LIMITS)}
        finding['finding_id']='finding:'+c.digest(finding)
        findings.append(finding)

    emit('packet_binding','PASS','CONTRACT_AND_DIGESTS_VALID',c.SCHEMA_VERSION,packet['schema_version'])
    allowed_policy={'id','version','max_age_seconds','required_capabilities'}
    supported=policy['id']=='synthetic-quote-freshness' and not (set(policy)-allowed_policy) and set(policy['required_capabilities'])==REQUIRED_CAPABILITIES
    emit('policy_scope','PASS' if supported else 'INCONCLUSIVE',
        'AUTHORED_POLICY_SCOPE' if supported else 'POLICY_OBLIGATIONS_NOT_IMPLEMENTED',
        {'id':'synthetic-quote-freshness','implemented_fields':sorted(allowed_policy),'required_capabilities':sorted(REQUIRED_CAPABILITIES)},policy)
    capture={cap['name']:cap for cap in packet['capabilities']}
    for name in sorted(REQUIRED_CAPABILITIES | set(policy['required_capabilities'])):
        state=capture.get(name,{}).get('state','UNKNOWN')
        emit('capture:'+name,'PASS' if state=='CAPTURED' else 'INCONCLUSIVE',
             'CAPTURE_DECLARED' if state=='CAPTURED' else 'CAPTURE_UNKNOWN_OR_UNAVAILABLE',
             'CAPTURED within declared fixture scope',state)

    clocks={}
    for name,value in [('as_of',proposal['as_of']),('created_at',proposal['created_at']),('context_observed_at',context['observed_at'])]:
        clocks[name]=c.parse_time(value)
    known=all(value is not None for value in clocks.values())
    order=known and clocks['context_observed_at']<=clocks['created_at']<=clocks['as_of']
    emit('decision_clocks','INCONCLUSIVE' if not known else ('PASS' if order else 'FAIL'),
         'DECISION_CLOCK_MISSING' if not known else ('DECISION_CLOCKS_ORDERED' if order else 'FUTURE_CONTEXT_OR_PROPOSAL'),
         'context observed <= proposal created <= decision as-of',{'declared':{'context':context['observed_at'],'created_at':proposal['created_at'],'as_of':proposal['as_of']}})
    as_of,context_time=clocks['as_of'],clocks['context_observed_at']
    refs=set(context['event_refs'])
    protocol=bool(refs) and proposal['call_id'] in refs and bool(set(proposal['causal_refs']) & refs)
    emit('proposal_observed_prefix','PASS' if protocol else 'INCONCLUSIVE',
         'PROPOSAL_IN_DECLARED_PREFIX' if protocol else 'PROPOSAL_PREFIX_CAPTURE_INCOMPLETE',
         'submission call and at least one proposal causal reference in declared prefix',
         {'call_id':proposal['call_id'],'event_refs':context['event_refs'],'causal_refs':proposal['causal_refs']})
    visible={}
    for evidence in packet['evidence']:
        values=[c.parse_time(evidence[k]) for k in ('valid_at','retrieved_at','recorded_at')]
        complete=all(t is not None for t in values) and as_of is not None and context_time is not None
        ordered=complete and values[0]<=values[1]<=values[2]<=context_time<=as_of
        causal=bool(set(evidence['causal_refs']) & refs)
        status='INCONCLUSIVE' if not complete or not causal else ('PASS' if ordered else 'FAIL')
        reason='EVIDENCE_CLOCK_OR_CAPTURE_MISSING' if status=='INCONCLUSIVE' else ('EVIDENCE_VISIBLE_IN_PREFIX' if ordered else 'FUTURE_OR_MISORDERED_EVIDENCE')
        visible[evidence['id']]=bool(ordered and causal)
        emit('evidence_observed_prefix',status,reason,
             'valid <= retrieved <= recorded <= context observed <= as-of, with observed causal reference',
             {'valid_at':evidence['valid_at'],'retrieved_at':evidence['retrieved_at'],'recorded_at':evidence['recorded_at'],'observed_causal_reference':causal},evidence)

    dependencies=proposal['dependencies']
    complete=proposal['dependency_completeness']=='COMPLETE' and dependencies is not None
    narrow=complete and len(dependencies)==1 and len(proposal['extracts'])==1
    emit('dependency_coverage','PASS' if narrow else 'INCONCLUSIVE',
         'DECLARED_FIXTURE_DEPENDENCIES_COMPLETE' if narrow else 'DEPENDENCY_COVERAGE_INCOMPLETE_OR_OUTSIDE_MAPPING',
         'COMPLETE declared one-observation fixture dependency and one extract',
         {'dependency_completeness':proposal['dependency_completeness'],'dependencies':dependencies,'extract_count':len(proposal['extracts'])})
    by_id={e['id']:e for e in packet['evidence']}
    declared={d['evidence_id']:d for d in dependencies or []}
    for dep in dependencies or []:
        evidence=by_id.get(dep['evidence_id'])
        if evidence is None:
            emit('dependency_binding','INCONCLUSIVE','DEPENDENCY_EVIDENCE_MISSING',dep,None)
            continue
        declared_status=dep['status']=='DECLARED'
        matches=dep['source_version']==evidence['source_version']
        emit('dependency_binding','INCONCLUSIVE' if not declared_status else ('PASS' if matches else 'FAIL'),
            'DEPENDENCY_PROVISIONAL' if not declared_status else ('DEPENDENCY_VERSION_MATCH' if matches else 'DEPENDENCY_VERSION_MISMATCH'),
            {'status':'DECLARED','source_version':evidence['source_version']},dep,evidence)
        available=evidence['status']=='AVAILABLE'
        emit('source_availability','PASS' if available else 'INCONCLUSIVE',
             'SOURCE_OBSERVATION_AVAILABLE' if available else 'NO_DATA_NOT_AN_OBSERVATION',
             'AVAILABLE price observation',evidence['status'],evidence)
        if evidence['valid_at'] is None or as_of is None:
            emit('freshness','INCONCLUSIVE','FRESHNESS_CLOCK_MISSING','0 <= age < max_age_seconds',None,evidence)
        else:
            try:
                begin,end=_expiry(evidence['valid_at'],policy['max_age_seconds'])
                fresh=begin<=as_of<end
                emit('freshness','PASS' if fresh else 'FAIL',
                     'EVIDENCE_FRESH' if fresh else ('EVIDENCE_NOT_YET_VALID' if as_of<begin else 'EVIDENCE_EXPIRED'),
                     {'eligible_from_inclusive':begin.isoformat(),'expires_at_exclusive':end.isoformat()},
                     {'age_seconds':(as_of-begin).total_seconds(),'max_age_seconds':policy['max_age_seconds'],'as_of':proposal['as_of']},evidence)
            except (MissingPrerequisite,InvalidBinding) as exc:
                emit('freshness','ERROR' if isinstance(exc,InvalidBinding) else 'INCONCLUSIVE',str(exc).upper(),
                     'Finite computable authored expiry',policy['max_age_seconds'],evidence)
        superseders=[e for e in packet['evidence'] if evidence['id'] in e['supersedes'] and visible[e['id']]]
        wrong_source=[e for e in superseders if e['source_id']!=evidence['source_id']]
        emit('known_supersession','ERROR' if wrong_source else ('FAIL' if superseders else 'PASS'),
             'SUPERSESSION_SOURCE_BINDING_INVALID' if wrong_source else ('KNOWN_SUPERSEDED_VERSION' if superseders else 'NO_KNOWN_VISIBLE_SUPERSEDER'),
             'No visible same-source replacement of this cited observation',
             {'visible_superseders':[e['id'] for e in superseders]},evidence,
             negative=[_anchor(e) for e in superseders] if superseders else [])

    for extract in proposal['extracts']:
        evidence=by_id.get(extract['evidence_id'])
        if evidence is None:
            emit('extract_binding','INCONCLUSIVE','EXTRACT_EVIDENCE_MISSING',extract['evidence_id'],None,extract=extract)
            continue
        dep=declared.get(evidence['id'])
        if dep is None:
            emit('extract_dependency','INCONCLUSIVE','EXTRACT_DEPENDENCY_NOT_DECLARED','declared material dependency',None,evidence,extract)
        versions=extract['source_version']==evidence['source_version'] and (dep is None or dep['source_version']==extract['source_version'])
        emit('extract_version','PASS' if versions else 'FAIL',
             'EXTRACT_VERSION_MATCH' if versions else 'EXTRACT_SOURCE_VERSION_MISMATCH',evidence['source_version'],extract['source_version'],evidence,extract)
        lo,hi=extract['span']
        span_ok=lo<hi and evidence['pointer']['span'][0]<=lo<hi<=evidence['pointer']['span'][1] and evidence['content'][lo:hi]==extract['quote']
        emit('extract_span','PASS' if span_ok else 'FAIL',
             'EXACT_EXTRACT_SPAN' if span_ok else 'EXTRACT_QUOTE_OR_SPAN_MISMATCH',
             {'span':extract['span'],'quote':evidence['content'][lo:hi]},extract['quote'],evidence,extract)
        match=_QUOTE.fullmatch(evidence['content'])
        supported=extract['field']=='observed_quote' and match is not None and evidence['status']=='AVAILABLE'
        if not supported:
            emit('extract_mapping','INCONCLUSIVE','AUTHORED_MAPPING_UNRESOLVED',
                 'Authored Synthetic ETH-USD quote template and observed_quote field',{'field':extract['field'],'template_match':match is not None},evidence,extract)
            continue
        if extract['unit'] is None:
            emit('extract_unit','INCONCLUSIVE','EXTRACT_UNIT_MISSING','USD',None,evidence,extract)
        else:
            emit('extract_unit','PASS' if extract['unit']=='USD' else 'FAIL',
                 'EXTRACT_UNIT_MATCH' if extract['unit']=='USD' else 'EXTRACT_UNIT_MISMATCH','USD',extract['unit'],evidence,extract)
        field_span=extract['span']==list(match.span('amount'))
        emit('extract_field_alignment','PASS' if field_span else 'FAIL',
             'EXACT_AUTHORED_VALUE_FIELD' if field_span else 'EXTRACT_WRONG_VALUE_FIELD',list(match.span('amount')),extract['span'],evidence,extract)
        try:
            source_value=_scalar(match.group('amount'))
            submitted_value=_scalar(extract['value'])
            equal=source_value==submitted_value
            emit('extract_value','PASS' if equal else 'FAIL',
                 'EXTRACT_VALUE_MATCH' if equal else 'EXTRACT_VALUE_MISMATCH',str(source_value),str(submitted_value),evidence,extract)
        except (MissingPrerequisite,InvalidBinding) as exc:
            emit('extract_value','ERROR' if isinstance(exc,InvalidBinding) else 'INCONCLUSIVE',str(exc).upper(),
                 'Finite explicitly formatted scalar',extract['value'],evidence,extract)
        try:
            text_time=_utc(match.group('instant'))
            declared_time=_utc(evidence['valid_at'])
            equal=text_time==declared_time
            emit('valid_time_source_alignment','PASS' if equal else 'FAIL',
                 'VALID_TIME_MATCHES_SOURCE_TEXT' if equal else 'VALID_TIME_TEXT_MISMATCH',
                 match.group('instant'),evidence['valid_at'],evidence,extract)
        except (MissingPrerequisite,InvalidBinding) as exc:
            emit('valid_time_source_alignment','ERROR' if isinstance(exc,InvalidBinding) else 'INCONCLUSIVE',str(exc).upper(),
                 'Explicit source/declaration valid-time mapping',evidence['valid_at'],evidence,extract)
        proposal_match=re.fullmatch(r'REVIEW_ONLY synthetic paper proposal; quote observation (\S+) USD\. No trade authority\.',proposal['text'])
        proposal_aligned=False
        if proposal_match:
            try:proposal_aligned=_scalar(proposal_match.group(1))==_scalar(extract['value'])
            except (MissingPrerequisite,InvalidBinding):pass
        emit('proposal_extract_alignment','PASS' if proposal_aligned else 'INCONCLUSIVE',
             'AUTHORED_PROPOSAL_MATCH' if proposal_aligned else 'PROPOSAL_EXTRACT_MAPPING_UNRESOLVED',
             'One authored paper-quote assertion matching submitted extract',proposal['text'],evidence,extract)
    return _finish(packet,binding,findings)


def validate_clearance(clearance,packet):
    """Reject changed/reused/forged local clearances by current reassessment.

    Reassessment is required, not merely digest comparison. This does not
    establish issuer authentication or act as a real framework enforcement hook.
    """
    if not isinstance(clearance,dict):
        return False
    try:
        if not c.binding_matches(clearance.get('binding'),packet):
            return False
        current=assess(packet)
        return current['clearance'] is not None and c.canonical_json(clearance)==c.canonical_json(current['clearance'])
    except (ValueError,TypeError,KeyError,OverflowError,UnicodeError):
        return False
