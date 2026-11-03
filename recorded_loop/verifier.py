"""Scoped historical-source/reviewer verification; no historical writes or models.

The shared source packet belongs to source_adapter. Internal scalar/CSV helpers
are independent of that packet shape. Historical artifacts are never imported
as runnable builders or modified here.
"""
from decimal import Decimal
import csv
import io
import re
import copy
import hashlib
import uuid
from datetime import datetime
from pathlib import Path

from recorded_loop import source_adapter as sa


VERIFIER_VERSION='recorded-source-verifier-0.1'
POLICY_VERSION='recorded-historical-and-review-policy-0.1'
ORIGINAL_SCOPE='selected_original_recorded_call_checks_with_explicit_unknowns'
REVIEW_SCOPE='new_local_reviewer_snapshot_availability_and_selected_consistency_only'
LIMITS=[
    'Actual recorded model execution over synthetic frozen market evidence, not live ETH history.',
    'Selected source-linked checks do not certify full-decision dependencies, Hold suitability or semantic completeness.',
    'Content in a recorded call is not private attention/reliance or automatically direct tool-message lineage.',
    'Post-hoc reviewer reads do not change historical invocation, feedback, source versions or original agent responses.',
    'For Sol the full sentence is source context: only close-below-open/previous conjuncts are checked; higher-high wording remains unassessed.',
]


def _policy_binding():
    here=Path(__file__)
    return {'verifier_version':VERIFIER_VERSION,'policy_version':POLICY_VERSION,
        'verifier_sha256':hashlib.sha256(here.read_bytes()).hexdigest(),
        'policy_sha256':hashlib.sha256(here.with_name('POLICY.md').read_bytes()).hexdigest()}


def _instant(value):
    if value is None:
        raise UnresolvedPrerequisite('timestamp_missing')
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})',value) or value.endswith('-00:00'):
        raise InvalidSourceBinding('timestamp_invalid')
    try:return datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:raise InvalidSourceBinding('timestamp_invalid') from exc


class UnresolvedPrerequisite(ValueError):
    pass


class InvalidSourceBinding(ValueError):
    pass


def _decimal(value):
    if value is None:
        raise UnresolvedPrerequisite('numeric_value_missing')
    if not isinstance(value,str) or not re.fullmatch(r'[+-]?(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?',value):
        raise InvalidSourceBinding('numeric_value_invalid')
    return Decimal(value.replace(',',''))


def _price_row(content,valid_date):
    if valid_date is None:
        raise UnresolvedPrerequisite('date_mapping_missing')
    if not isinstance(content,str) or not content.startswith('Synthetic OHLCV CSV, USD\n'):
        raise UnresolvedPrerequisite('price_unit_or_csv_mapping_unresolved')
    rows=list(csv.DictReader(io.StringIO(content.split('\n',1)[1])))
    matches=[r for r in rows if r.get('Date')==valid_date]
    if len(matches)!=1:
        raise UnresolvedPrerequisite('dated_row_not_unique_or_absent')
    row=matches[0]
    for key in ('Open','High','Low','Close'):
        if key not in row:
            raise UnresolvedPrerequisite('price_column_missing')
        _decimal(row[key])
    return row


def _snapshot_values(content):
    pattern=(r'Synthetic ETH-USD snapshot at (?P<date>\d{4}-\d{2}-\d{2}) close: '
             r'open=(?P<Open>\d+(?:\.\d+)?) high=(?P<High>\d+(?:\.\d+)?) '
             r'low=(?P<Low>\d+(?:\.\d+)?) close=(?P<Close>\d+(?:\.\d+)?) '
             r'volume=(?P<Volume>\d+(?:\.\d+)?)\. Recent closes: (?P<recent>[\d.,]+)\. Long-window indicators unavailable\.')
    match=re.fullmatch(pattern,content) if isinstance(content,str) else None
    if match is None:
        raise UnresolvedPrerequisite('snapshot_mapping_unresolved')
    values=match.groupdict()
    values['recent_closes']=values.pop('recent').split(',')
    for value in values['recent_closes']:
        _decimal(value)
    return values


def _status(findings):
    statuses={finding['status'] for finding in findings}
    return next((s for s in ('ERROR','FAIL','INCONCLUSIVE','NOT_APPLICABLE') if s in statuses),'PASS')


def _finding(packet,obligation,status,reason,expected,observed,witnesses=None,scope=ORIGINAL_SCOPE):
    source=packet.get('call_context',{}) if isinstance(packet,dict) else {}
    source=source if isinstance(source,dict) else {}
    before=source.get('input_event',{});before=before if isinstance(before,dict) else {}
    after=source.get('output_event',{});after=after if isinstance(after,dict) else {}
    finding={'obligation':obligation,'status':status,'reason_code':reason,'scope':scope,
        'method_version':VERIFIER_VERSION,'expected':expected,'observed':observed,
        'original_run_id':packet.get('run_id') if isinstance(packet,dict) else None,
        'original_input_seq':before.get('seq'),
        'original_output_seq':after.get('seq'),
        'source_witnesses':copy.deepcopy(witnesses or []),'limits':list(LIMITS)}
    finding['finding_id']='recorded-finding:'+sa.digest(finding)
    return finding


def _safe_packet_id(packet):
    value=packet.get('packet_id') if isinstance(packet,dict) else None
    if type(value) is str:
        try:value.encode('utf-8');return value
        except UnicodeError:pass
    return None


def _finish_original(packet,findings):
    protocol=next((f['status'] for f in findings if f['obligation']=='required_snapshot_invocation'),'ERROR')
    output={'packet_id':_safe_packet_id(packet),'layer':'historical_source_assessment',
        'scope':ORIGINAL_SCOPE,'status':_status(findings),'findings':findings,
        'protocol_status':protocol,'historical_protocol_status':protocol,
        'required_response':{'action':'retrieve_for_review','evidence_key':'E_SNAPSHOT',
            'historical_repair_performed':False},'clearance':None,
        'policy_binding':_policy_binding(),'limits':list(LIMITS)}
    output['assessment_id']='recorded-assessment:'+sa.digest(output)
    return output


def _validate_packet(packet):
    if not isinstance(packet,dict):
        raise InvalidSourceBinding('source_packet_not_an_object')
    for field in ('source','ledger_pin','report','claim','instruction','call_context','prefix','evidence','coverage'):
        if not isinstance(packet.get(field),dict):
            raise InvalidSourceBinding('source_packet_structure_invalid:'+field)
    if not isinstance(packet['claim'].get('mapping'),dict):
        raise InvalidSourceBinding('claim_mapping_structure_invalid')
    body=copy.deepcopy(packet);identity=body.pop('packet_id',None)
    if identity!='recorded-case:'+sa.digest(body):
        raise InvalidSourceBinding('source_packet_identity_mismatch')
    return sa.validate_case_sources(packet)


def _numeric_check(packet,content):
    """Compare only the declared selected mapping against dated CSV, not Hold."""
    claim=packet['claim'];mapping=claim['mapping']
    required=('entity','valid_date','unit','evidence_key','field','operator','scope','status')
    missing=[key for key in required if mapping.get(key) is None]
    if missing:
        return 'INCONCLUSIVE','MAPPING_PREREQUISITES_MISSING',{'missing':missing}
    scalar=claim['kind']=='scalar_close'
    if claim['kind'] not in ('scalar_close','relational_close'):
        return 'INCONCLUSIVE','CLAIM_MAPPING_NOT_IMPLEMENTED',{'kind':claim['kind']}
    expected={'entity':'ETH-USD','valid_date':'2026-10-28','unit':'USD','evidence_key':'E_PRICE',
        'field':'Close','operator':'equals' if scalar else 'lt_open_and_previous_close',
        'scope':'synthetic_fixture_consistency_only','status':'human_accepted_context_mapping' if scalar else 'authored_relational_mapping'}
    mismatch={key:{'expected':value,'observed':mapping.get(key)} for key,value in expected.items() if mapping.get(key)!=value}
    if mismatch:
        return 'FAIL','DECLARED_MAPPING_DISAGREES_WITH_SELECTED_CONTEXT',mismatch
    report=packet['report']['text'];anchor=claim['anchor']
    if scalar:
        selected=packet['run_id']=='terra-2f66dbe7f15d' and anchor['start']==346 and anchor['end']==351 and claim['quote']=='2,540'
        selected=selected and 'close of **$2,540**' in report and 'As of October 28, 2026.' in report and '# ETH-USD indicator report' in report
    else:
        selected=packet['run_id']=='sol-0530a9827c2c' and claim['quote']==sa.SOL_QUOTE and report.count(sa.SOL_QUOTE)==1
        selected=selected and '**As of October 28, 2026 | USD quote | Synthetic fixture only**' in report
    if not selected:
        return 'FAIL','SELECTED_CLAIM_ROLE_OR_CONTEXT_MISMATCH',{'kind':claim['kind'],'anchor':anchor}
    row=_price_row(content,mapping['valid_date'])
    if scalar:
        if mapping.get('value') is None:
            return 'INCONCLUSIVE','MAPPED_SCALAR_MISSING',{'value':None}
        source=_decimal(row['Close']);raw=_decimal(claim['quote']);mapped=_decimal(mapping['value'])
        equal=source==raw==mapped
        return ('PASS' if equal else 'FAIL'),('DATED_SCALAR_EQUAL' if equal else 'SCALAR_VALUE_MISMATCH'),{
            'csv_close':str(source),'raw_claim':str(raw),'mapped_value':str(mapped),'valid_date':mapping['valid_date'],'unit':mapping['unit']}
    previous=_price_row(content,'2026-10-27')
    checks={'below_open':_decimal(row['Close'])<_decimal(row['Open']),
            'below_previous_close':_decimal(row['Close'])<_decimal(previous['Close'])}
    return ('PASS' if all(checks.values()) else 'FAIL'),'DATED_SOL_RELATION_CHECKED',{
        'checks':checks,'close':row['Close'],'open':row['Open'],'previous_close':previous['Close'],
        'previous_date':'2026-10-27','valid_date':mapping['valid_date'],
        'checked_subclaims':['Close[2026-10-28] < Open[2026-10-28]','Close[2026-10-28] < Close[2026-10-27]'],
        'unassessed_subclaims':['The final session reaches a higher high'],
        'source_sentence_fully_verified':False,
        'scope_note':'Full selected sentence is source context; close-below-open/previous conjuncts only, higher-high conjunct unassessed.'}


def assess_original(packet):
    """Read-only source validation plus bounded historical findings.

    Full procedure clearance is always None. No original feedback is invented.
    """
    findings=[]
    try:
        integrity=_validate_packet(packet)
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OSError,OverflowError,UnicodeError,RecursionError) as exc:
        findings.append(_finding({},'source_binding','ERROR','INVALID_ORIGINAL_SOURCE_BINDING',
                                 'Pinned original files, packet identity and exact anchors',str(exc)))
        return _finish_original(packet,findings)
    packet=copy.deepcopy(packet)

    def emit(obligation,status,reason,expected,observed,witnesses=None):
        findings.append(_finding(packet,obligation,status,reason,expected,observed,witnesses))

    emit('source_binding','PASS','ORIGINAL_FILES_AND_ANCHORS_VALID',
         {'schema':sa.SCHEMA_VERSION,'ledger':sa.LEDGER_SHA},integrity,
         [packet['report']['anchor'],packet['claim']['anchor']])
    price=packet['evidence']['E_PRICE'];snapshot=packet['evidence']['E_SNAPSHOT']
    try:
        status,reason,observed=_numeric_check(packet,price['content'])
    except UnresolvedPrerequisite as exc:
        status,reason,observed='INCONCLUSIVE',str(exc).upper(),None
    except (InvalidSourceBinding,ValueError,KeyError,TypeError,IndexError) as exc:
        status,reason,observed='ERROR','NUMERIC_MAPPING_ERROR',str(exc)
    emit('selected_fixture_consistency',status,reason,
         'Selected accepted Terra scalar or authored actual Sol relation in dated USD fixture',observed,
         [packet['claim']['anchor'],price['anchor']])
    for key,item in [('E_PRICE',price),('E_SNAPSHOT',snapshot)]:
        exposures=item['access']['input_exposures']
        emit('original_call_exposure:'+key,'PASS' if exposures else 'INCONCLUSIVE',
             'EXACT_CONTENT_IN_ORIGINAL_INPUT' if exposures else 'NO_EXACT_FULL_CONTENT_MATCH_IDENTIFIED',
             'Exact source content tied to the selected original input, preserving decoded coordinate/role lineage',
             {'input_seq':packet['call_context']['input_event']['seq'],'occurrences':len(exposures),
              'exposures':exposures,'attention_or_reliance_established':False},[e['anchor'] for e in exposures])
    prefix=packet['prefix'];out=packet['call_context']['output_event']
    complete=packet['coverage'].get('tool_capture')=='complete_recorded_prefix_before_selected_market_report'
    complete=complete and [e['seq'] for e in prefix['events']]==list(range(1,out['seq']))
    calls=[e for e in prefix['events'] if e['kind']=='tool.start' and e['payload'].get('tool',{}).get('name')==packet['instruction']['required_tool']]
    captures=[row for row in prefix['tool_invocations'] if row['tool']==packet['instruction']['required_tool']]
    retrievals=[e for e in prefix['events'] if e['kind']=='evidence.retrieved' and e['payload'].get('evidence',{}).get('evidence_id')=='E_SNAPSHOT']
    protocol='INCONCLUSIVE' if not complete else ('PASS' if calls else 'FAIL')
    emit('required_snapshot_invocation',protocol,
         'ORIGINAL_TOOL_CAPTURE_INCOMPLETE' if not complete else ('ORIGINAL_REQUIRED_INVOCATION_PRESENT' if calls else 'ORIGINAL_REQUIRED_INVOCATION_OMITTED'),
         {'tool':packet['instruction']['required_tool'],'before_output_seq':out['seq']},
         {'invocation_seqs':[e['seq'] for e in calls],'retrieval_seqs':[e['seq'] for e in retrievals],
          'bounded_prefix':[prefix['seq_start'],prefix['seq_end_inclusive']],'capture_complete':complete},
         [packet['instruction']['anchor']]+[e['raw_ref'] for e in captures])
    date=packet['claim']['mapping'].get('valid_date')
    dates=[date,price.get('valid_date'),snapshot.get('valid_date')]
    known=all(value is not None for value in dates)
    aligned=known and len(set(dates))==1 and dates[0]=='2026-10-28'
    emit('historical_date_alignment','INCONCLUSIVE' if not known else ('PASS' if aligned else 'FAIL'),
         'HISTORICAL_DATE_UNKNOWN' if not known else ('SYNTHETIC_ASOF_DATE_ALIGNED' if aligned else 'HISTORICAL_DATE_MISMATCH'),
         'Declared synthetic historical as-of 2026-10-28, not current execution wall time',
         {'dates':dates,'actual_execution_timestamp':out['timestamp'],'wall_clock_not_substituted_for_market_asof':True},
         [packet['report']['anchor'],price['anchor'],snapshot['anchor']])
    emit('intraday_freshness','INCONCLUSIVE','INTRADAY_USE_PRECISION_AND_FRESHNESS_POLICY_UNAVAILABLE',
         'Explicit intraday intended use instant and accepted freshness policy',
         {'asof_precision':packet['claim']['mapping'].get('date_precision'),
          'fixture_observed_at':price['declared_observed_at'],'fixture_time_precision':price['observed_time_precision'],
          'ttl_applied':None,'source_version_progression_invented':False},[price['anchor']])
    emit('source_version_semantics','INCONCLUSIVE','SOURCE_VERSION_UNAVAILABLE_HASH_IS_NOT_VERSION_AUTHORITY',
         'Publisher/version semantics when a version claim is required',
         {'source_version':price['source_version'],'snapshot_identity':price['snapshot_identity']},[price['anchor']])
    emit('whole_decision_dependencies','INCONCLUSIVE','WHOLE_DECISION_DEPENDENCY_COMPLETENESS_UNESTABLISHED',
         'Established material dependencies for complete final decision',
         packet['coverage'].get('dependency_completeness'))
    emit('hold_suitability','INCONCLUSIVE','HOLD_POLICY_PORTFOLIO_AND_OBJECTIVES_NOT_CERTIFIED',
         'Actual portfolio, limits, objectives, horizon and sufficient decision rule',None)
    emit('original_agent_response','INCONCLUSIVE','NO_ORIGINAL_AGENT_RESPONSE_TO_NEW_REVIEW',
         'Observed original receiving input and acknowledgement/correction if claiming remediation',
         {'trustkernel_feedback':packet['source']['trustkernel_feedback'],
          'recorded_response_to_new_review':'UNOBSERVED','new_model_response_created':False})
    return _finish_original(packet,findings)


def assess(packet):
    return assess_original(packet)


def assess_review(packet,receipt):
    """Review a new local read receipt without clearing historical procedure."""
    historical=assess_original(packet)
    findings=[]

    def emit(obligation,status,reason,expected,observed,witnesses=None):
        findings.append(_finding(packet if isinstance(packet,dict) else {},obligation,status,reason,
                                 expected,observed,witnesses,REVIEW_SCOPE))

    valid_source=not any(f['status']=='ERROR' for f in historical['findings'])
    if not valid_source:
        emit('review_source_binding','ERROR','ORIGINAL_SOURCE_CANNOT_BE_BOUND',
             'Valid immutable original case',historical['assessment_id'])
    else:
        try:
            if not isinstance(receipt,dict):
                raise InvalidSourceBinding('review_receipt_not_an_object')
            body=copy.deepcopy(receipt);identity=body.pop('receipt_digest',None)
            if sa.digest(body)!=identity:
                raise InvalidSourceBinding('review_receipt_digest_mismatch')
            if receipt['layer']!='new_reviewer_retrieval' or receipt['actor']!='local_reviewer_replay':
                raise InvalidSourceBinding('reviewer_layer_or_actor_invalid')
            if not isinstance(receipt['receipt_id'],str) or not receipt['receipt_id'].startswith('review-retrieval:'):
                raise InvalidSourceBinding('new_reviewer_identity_missing')
            uuid.UUID(receipt['receipt_id'].split(':',1)[1])
            if receipt['source_packet_id']!=packet['packet_id'] or receipt['source_run_id']!=packet['run_id']:
                raise InvalidSourceBinding('review_receipt_wrong_original_case')
            if receipt['evidence_key']!='E_SNAPSHOT':
                raise InvalidSourceBinding('review_receipt_wrong_evidence_scope')
            if receipt['original_history_modified'] is not False or receipt['historical_tool_invocation_created'] is not False:
                raise InvalidSourceBinding('review_receipt_falsely_changes_history')
            evidence=packet['evidence']['E_SNAPSHOT']
            expected={'content':evidence['content'],'content_digest':evidence['content_digest'],
                'source_anchor':evidence['anchor'],'source_version':None,'snapshot_identity':evidence['snapshot_identity'],
                'source_origin':packet['source']['fixture_origin'],'source_observed_at':evidence['declared_observed_at']}
            for key,value in expected.items():
                if receipt.get(key)!=value:
                    raise InvalidSourceBinding('review_original_'+key+'_binding_mismatch')
            if sa.digest(receipt['content'])!=receipt['content_digest']:
                raise InvalidSourceBinding('review_evidence_content_digest_mismatch')
            if _instant(receipt['retrieved_at'])<=_instant(packet['call_context']['output_event']['timestamp']):
                raise InvalidSourceBinding('review_receipt_backdated_into_original_execution')
            emit('review_receipt_binding','PASS','NEW_LOCAL_RECEIPT_BOUND_TO_UNCHANGED_SOURCE',
                 'New reviewer identity/time and exact original case/source/digests; no historical event creation',
                 {'receipt_id':receipt['receipt_id'],'retrieved_at':receipt['retrieved_at'],'receipt_digest':identity},[receipt['source_anchor']])
            emit('posthoc_snapshot_availability','PASS','ORIGINAL_SNAPSHOT_ARTIFACT_READ_ONLY_AVAILABLE',
                 'Repository artifact available in new local reviewer scope',
                 {'source_version':None,'snapshot_identity':receipt['snapshot_identity'],
                  'current_market_refresh_established':False,'original_input_delivery_created':False},[receipt['source_anchor']])
            values=_snapshot_values(receipt['content'])
            price=packet['evidence']['E_PRICE'];date=packet['claim']['mapping'].get('valid_date')
            row=_price_row(price['content'],date)
            date_ok=values['date']==date==price['valid_date']=='2026-10-28'
            numeric_ok=all(_decimal(values[key])==_decimal(row[key]) for key in ('Open','High','Low','Close'))
            emit('posthoc_snapshot_csv_consistency','PASS' if date_ok and numeric_ok else 'FAIL',
                 'DATED_SNAPSHOT_CSV_MATCH' if date_ok and numeric_ok else 'DATED_SNAPSHOT_CSV_MISMATCH',
                 'Same dated synthetic OHLC price fields only; no independent corroboration',
                 {'valid_date':date,'snapshot_date':values['date'],'fields_match':numeric_ok},[receipt['source_anchor'],price['anchor']])
            status,reason,observed=_numeric_check(packet,price['content'])
            if packet['claim']['kind']=='scalar_close':
                relation_ok=_decimal(values['Close'])==_decimal(packet['claim']['quote'])
            else:
                recent=values['recent_closes']
                if len(recent)<2:
                    raise UnresolvedPrerequisite('snapshot_previous_close_unavailable')
                previous=_price_row(price['content'],'2026-10-27')
                relation_ok=_decimal(recent[-2])==_decimal(previous['Close']) and _decimal(values['Close'])<_decimal(values['Open']) and _decimal(values['Close'])<_decimal(recent[-2])
            if status=='PASS' and not relation_ok:
                status,reason='FAIL','SELECTED_CLAIM_SNAPSHOT_MISMATCH'
            emit('posthoc_selected_claim_consistency',status,reason,
                 'Only the selected scalar/close-below relation, under retained mapping',observed,
                 [packet['claim']['anchor'],receipt['source_anchor'],price['anchor']])
        except UnresolvedPrerequisite as exc:
            emit('review_prerequisites','INCONCLUSIVE',str(exc).upper(),'Known selected review prerequisite',None)
        except (ValueError,TypeError,KeyError,IndexError,OSError,OverflowError,UnicodeError,RecursionError) as exc:
            emit('review_receipt_binding','ERROR','INVALID_REVIEW_RECEIPT_BINDING',
                 'New read receipt bound to exact original case and source',str(exc))
    result_status=_status(findings)
    ready=result_status=='PASS' and len(findings)==4
    binding=None
    if ready:
        binding={'scope':REVIEW_SCOPE,'source_packet_id':packet['packet_id'],
            'source_packet_digest':sa.digest(packet),'source_files_digest':sa.digest(packet['source_files']),
            'receipt_id':receipt['receipt_id'],'receipt_digest':receipt['receipt_digest'],
            'historical_assessment_id':historical['assessment_id'],'policy_binding':_policy_binding(),
            'historical_procedure_cleared':False,'trading_authority':False}
    output={'packet_id':_safe_packet_id(packet),'layer':'new_reviewer_assessment','scope':REVIEW_SCOPE,
        'review_scope':REVIEW_SCOPE,'status':result_status,'findings':findings,'review_ready':ready,
        'readiness_binding':binding,'historical_assessment_id':historical['assessment_id'],
        'historical_protocol_status':historical['protocol_status'],'protocol_status':historical['protocol_status'],
        'historical_clearance':None,'clearance':None,'policy_binding':_policy_binding(),'limits':list(LIMITS)}
    output['assessment_id']='recorded-review:'+sa.digest(output)
    return output
