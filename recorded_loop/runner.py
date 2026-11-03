"""Execute a read-only verification replay on actual recorded framework logs."""
import argparse
import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from procedural_loop.recording import Recorder, inspect_recording, query
from .audit import audit_sources
from .preservation import ROOT, capture, assert_preserved

CASES=('sol-0530a9827c2c','terra-2f66dbe7f15d')


def implementation_hashes():
    return {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'recorded_loop').rglob('*'))
            if p.is_file() and p.suffix in {'.py','.json','.md'} and '__pycache__' not in p.parts}


def write_json(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def run_case(source_run_id,directory,replay_run_id):
    from .source_adapter import build_case,retrieve_for_review,digest,validate_case_sources
    from .verifier import assess_original,assess_review
    packet=build_case(source_run_id)
    before=digest(packet)
    directory=Path(directory)
    with Recorder(directory,replay_run_id) as recorder:
        recorder.emit('run.start',{'mode':'read_only_recorded_log_replay','source_run_id':source_run_id,
            'source_model':packet['source']['model'],'new_model_calls':0,
            'original_evidence_origin':'frozen_synthetic_fixture','new_actor':'local_reviewer_replay',
            'original_agent_feedback_enabled':False,'historical_agent_remediation':'UNOBSERVED'})
        recorder.emit('source.case.bound',{'packet':packet,'source_integrity':validate_case_sources(packet)})
        original=assess_original(packet)
        recorder.emit('historical.assessment.completed',original)
        for finding in original['findings']:
            recorder.emit('historical.finding.recorded',finding)
        expected='FAIL' if source_run_id.startswith('sol-') else 'PASS'
        if original['protocol_status']!=expected or original.get('clearance') is not None:
            raise AssertionError('UNEXPECTED_HISTORICAL_PROTOCOL_OR_CLEARANCE')
        write_json(directory/'original-packet.json',packet)
        write_json(directory/'historical-assessment.json',original)

        recorder.emit('review.feedback.delivered',{'layer':'new_local_reviewer_event',
            'historical_assessment_id':original['assessment_id'],'source_packet_id':packet['packet_id'],
            'historical_protocol_status':original['protocol_status'],
            'request':'Read original E_SNAPSHOT artifact and recheck selected historical claim; preserve original findings.',
            'original_agent_delivery':'UNOBSERVED'})
        recorder.emit('review.feedback.acknowledged',{'layer':'new_local_reviewer_event','actor':'local_reviewer_replay',
            'historical_assessment_id':original['assessment_id'],
            'response':'Perform local evidence read and scoped post-hoc consistency review.',
            'original_agent_acknowledgement':'UNOBSERVED'})
        recorder.emit('review.artifact.requested',{'evidence_key':'E_SNAPSHOT','source_packet_id':packet['packet_id'],
            'purpose':'post_hoc_historical_claim_review','current_market_refresh':False})
        receipt=retrieve_for_review(packet,'E_SNAPSHOT')
        recorder.emit('review.artifact.retrieved',receipt)
        reviewed=assess_review(packet,receipt)
        recorder.emit('review.assessment.completed',reviewed)
        for finding in reviewed['findings']:
            recorder.emit('review.finding.recorded',finding)
        if reviewed['status']!='PASS' or not reviewed['review_ready']:
            raise AssertionError('POSTHOC_REVIEW_NOT_READY')
        if reviewed['historical_protocol_status']!=expected or reviewed.get('historical_clearance') is not None or reviewed.get('clearance') is not None:
            raise AssertionError('REVIEW_IMPROPERLY_CLEARED_HISTORICAL_PROCEDURE')
        if reviewed['historical_assessment_id']!=original['assessment_id']:
            raise AssertionError('REVIEW_LOST_HISTORICAL_ASSESSMENT_BINDING')
        after=assess_original(packet)
        if after!=original or digest(packet)!=before:
            raise AssertionError('HISTORICAL_PACKET_OR_ASSESSMENT_REWRITTEN')
        recorder.emit('historical.finding.preserved',{'status':'PASS','assessment_id':after['assessment_id'],
            'protocol_status':after['protocol_status'],'original_agent_remediation':'UNOBSERVED'})

        # Explicit negative control: the new read cannot masquerade as original agent history.
        impersonated=copy.deepcopy(receipt)
        impersonated['actor']='original_agent'
        impersonated['layer']='original_recorded_execution'
        if 'receipt_digest' in impersonated:
            body=dict(impersonated);body.pop('receipt_digest');impersonated['receipt_digest']=digest(body)
        rejected=assess_review(packet,impersonated)
        recorder.emit('negative_control.assessed',{'control':'review_receipt_impersonates_original_agent',
            'receipt':impersonated,'assessment':rejected})
        if rejected.get('review_ready') or rejected.get('status')=='PASS':
            raise AssertionError('ORIGINAL_AGENT_IMPERSONATION_ACCEPTED')
        write_json(directory/'review-receipt.json',receipt)
        write_json(directory/'review-assessment.json',reviewed)
        summary={'status':'COMPLETE_REVIEW_REPLAY','source_run_id':source_run_id,'replay_run_id':replay_run_id,
            'original_assessment_status':original['status'],'original_protocol_status':original['protocol_status'],
            'posthoc_review_status':reviewed['status'],'review_ready':reviewed['review_ready'],
            'review_scope':reviewed['review_scope'],'historical_protocol_unchanged':True,
            'historical_agent_remediation':'UNOBSERVED','new_model_calls':0,
            'current_market_freshness':'NOT_ESTABLISHED','trade_execution':False,
            'source_packet_id':packet['packet_id'],'historical_assessment_id':original['assessment_id'],
            'review_assessment_id':reviewed['assessment_id']}
        recorder.emit('run.end',summary)
        write_json(directory/'summary.json',summary)
    write_json(directory/'trace-validation.json',inspect_recording(directory))
    return summary


def execute(output_root=None):
    before=capture()
    implementation_before=implementation_hashes()
    original_audit=audit_sources()
    now=datetime.now(timezone.utc)
    run_id='recorded-verification-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    directory=(Path(output_root) if output_root else ROOT/'runs')/run_id
    directory.mkdir(parents=True,exist_ok=False)
    write_json(directory/'protected-inputs-before.json',before)
    write_json(directory/'original-source-audit.json',original_audit)
    try:
        cases=[run_case(case,directory/case,f'{run_id}:{case}') for case in CASES]
        preservation=assert_preserved(before)
        source_hashes=implementation_hashes()
        if source_hashes!=implementation_before:
            raise AssertionError('REPLAY_IMPLEMENTATION_CHANGED_DURING_RUN')
        manifest={'status':'COMPLETE_REVIEW_REPLAY','run_id':run_id,'started_at':now.isoformat(),
            'ended_at':datetime.now(timezone.utc).isoformat(),'cases':cases,'preservation':preservation,
            'original_runs_audited':len(original_audit['runs']),'original_events_audited':original_audit['total_events'],
            'selected_case_count':len(cases),'source_hashes':source_hashes,
            'new_model_calls':0,'external_network_calls':0,'spend_usd':'0','trade_execution':False,
            'historical_agent_remediation':'UNOBSERVED',
            'limits':['Actual recorded model logs over synthetic frozen market data.',
                'New actions are local reviewer replay, not original agent feedback, new market data or revised model decisions.',
                'Sol original protocol failure persists; narrow post-hoc review PASS never grants historical/trading clearance.']}
        write_json(directory/'experiment.json',manifest)
        lines=['# Recorded-log verification replay','',f'Run `{run_id}`: **COMPLETE_REVIEW_REPLAY**.','',
            'Actual TradingAgents/LangChain recordings are assessed; new feedback and artifact reads belong to a separate local reviewer.',
            '', '| Original case | Historical assessment | Original snapshot protocol | New post-hoc review | Historical agent remediation |',
            '|---|---|---|---|---|']
        for case in cases:
            lines.append(f"| {case['source_run_id']} | {case['original_assessment_status']} | {case['original_protocol_status']} | {case['posthoc_review_status']} | UNOBSERVED |")
        lines += ['',f"All {len(original_audit['runs'])} source traces / {original_audit['total_events']} events pass hash-chain and SQLite parity audit.",
            f"Protected assets unchanged: {preservation['unchanged_files']}.",'',
            'Sol original FAIL remains FAIL after the new snapshot artifact read. Terra original protocol PASS does not certify full reasoning or suitability.',
            'Daily fixture-date alignment is distinct from unknown intraday/current-market freshness. No synthetic TTL60 is applied.',
            'Source files, original call/event identities, spans and decode transformations are retained in each original-packet.json.',
            'Each case has JSONL/SQLite/console output plus original and review assessments. No model/API calls or trading actions occurred.']
        (directory/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print(f'\nRECORDED LOG REVIEW REPLAY COMPLETE: {directory}',flush=True)
        return directory
    except BaseException as exc:
        write_json(directory/'failure.json',{'status':'ERROR','error_type':type(exc).__name__,'message':str(exc),
            'preservation':assert_preserved(before)})
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    run=subs.add_parser('run');run.add_argument('--output-root',type=Path)
    inspect=subs.add_parser('inspect');inspect.add_argument('--run',type=Path,required=True)
    inspect.add_argument('--kind');inspect.add_argument('--limit',type=int,default=30)
    args=parser.parse_args()
    if args.command=='run':execute(args.output_root)
    else:print(json.dumps(query(args.run,args.kind,args.limit),indent=2,ensure_ascii=False))


if __name__=='__main__':main()
