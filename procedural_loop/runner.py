"""Run an offline scripted evidence-refresh verification loop, with no inference."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .recording import Recorder, canonical, inspect_recording, query
from .preservation import ROOT, protected_hashes, assert_preserved


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def run_one(shape, directory, run_id):
    from .adapters import ReplaySession, EXPIRED_AS_OF, REFRESH_AS_OF
    from .contracts import require_valid_packet
    from .verifier import assess, validate_clearance

    session = ReplaySession(shape, run_id=run_id)
    results = []
    directory = Path(directory)
    with Recorder(directory, run_id) as recorder:
        recorder.emit('run.start', {'mode':'offline_scripted_research','shape':shape,
            'model':None,'effort':None,'paid_calls':0,'trade_execution':False,
            'scope':'Authored fixture evidence procedure; no real agent/framework enforcement.'})

        def drain():
            for event in session.drain_events():
                recorder.emit('adapter.'+event['kind'], event, as_of=event['as_of'])

        def check(phase, packet):
            require_valid_packet(packet)
            for retained in results:
                require_valid_packet(packet, previous=retained['packet'])
            drain()
            recorder.emit('proposal.submitted', {'phase':phase,'packet':packet}, as_of=packet['proposal']['as_of'])
            result = assess(packet)
            recorder.emit('assessment.completed', {'phase':phase,**result}, as_of=packet['proposal']['as_of'])
            for finding in result['findings']:
                recorder.emit('finding.recorded', {'phase':phase,**finding}, as_of=packet['proposal']['as_of'])
            write_json(directory/f'{phase}-packet.json',packet)
            write_json(directory/f'{phase}-assessment.json',result)
            results.append({'phase':phase,'packet':packet,'assessment':result})
            return result

        initial = session.initial_packet()
        first = check('initial',initial)
        if first['clearance'] is None or not validate_clearance(first['clearance'],initial):
            raise AssertionError('INITIAL_ELIGIBLE_PACKET_NOT_CLEARED')
        recorder.emit('host.clearance.accepted', {'phase':'initial','status':'PASS','clearance':first['clearance']})

        expired = session.advance_to(EXPIRED_AS_OF)
        old_reuse_rejected = not validate_clearance(first['clearance'],expired)
        recorder.emit('host.old_clearance.checked', {'status':'PASS' if old_reuse_rejected else 'FAIL',
            'old_clearance_reuse_rejected':old_reuse_rejected})
        if not old_reuse_rejected:
            raise AssertionError('OLD_CLEARANCE_REUSED_AT_LATER_BOUNDARY')
        blocked = check('expired',expired)
        if blocked['clearance'] is not None or not blocked['required_response']:
            raise AssertionError('STALE_PACKET_NOT_BLOCKED_WITH_RESPONSE')
        recorder.emit('host.proposal.held', {'status':'HELD','assessment_id':blocked['assessment_id'],
            'scope':'Simulated paper research boundary only; no trading authority.'})
        session.deliver_finding(blocked)
        drain()
        recorder.emit('host.refresh.requested', {'required_response':blocked['required_response'],
            'assessment_id':blocked['assessment_id']}, as_of=REFRESH_AS_OF)
        session.request_refresh(REFRESH_AS_OF)
        drain()
        refreshed = session.revised_packet()
        last = check('refreshed',refreshed)
        if last['clearance'] is None or not validate_clearance(last['clearance'],refreshed):
            raise AssertionError('REFRESHED_PACKET_NOT_CLEARED')
        if validate_clearance(first['clearance'],refreshed):
            raise AssertionError('OLD_CLEARANCE_ACCEPTED_AFTER_REFRESH')
        recorder.emit('host.clearance.accepted', {'phase':'refreshed','status':'PASS',
            'clearance':last['clearance'],'supersedes_assessment_id':blocked['assessment_id']})

        # Negative controls are isolated mutations, never silently replacing the primary proposal.
        negative = copy.deepcopy(refreshed)
        negative['packet_id'] += ':distorted-value-control'
        negative['proposal']['revision'] += 100
        negative['proposal']['extracts'][0]['value'] = '9999'
        mutation = assess(negative)
        recorder.emit('negative_control.assessed', {'control':'distorted_extract_value',
            'packet':negative,'assessment':mutation})
        if mutation['clearance'] is not None or not any(f.get('status')=='FAIL' or f.get('result',{}).get('status')=='FAIL' for f in mutation['findings']):
            raise AssertionError('DISTORTED_EXTRACT_NOT_DETECTED')

        unseen = {e['source_version'] for e in initial['evidence']}
        if len(unseen)!=1 or len(expired['evidence'])!=len(initial['evidence']):
            raise AssertionError('FUTURE_REVISION_LEAKED_BEFORE_REFRESH')
        summary = {'shape':shape,'run_id':run_id,'status':'COMPLETE',
            'phases':[{'phase':r['phase'],'assessment_id':r['assessment']['assessment_id'],
                       'status':r['assessment']['status'],'cleared':r['assessment']['clearance'] is not None,
                       'source_versions':[e['source_version'] for e in r['packet']['evidence']]} for r in results],
            'old_clearance_reuse_rejected':old_reuse_rejected,
            'distorted_extract_rejected':mutation['clearance'] is None,
            'refresh_response_recorded':True,'model_calls':0,'trade_execution':False,
            'limits':['Scripted fixture actors, not live model behavior or Claude integration.',
                      'Clearance is for declared narrow evidence obligations, not trading suitability.',
                      'Authored freshness policy and declared dependency completeness are fixture assumptions.']}
        recorder.emit('run.end', summary)
        write_json(directory/'summary.json',summary)
    audit = inspect_recording(directory)
    write_json(directory/'trace-validation.json',audit)
    return summary


def signatures(directory):
    result = []
    for phase in ('initial','expired','refreshed'):
        assessment = json.loads((directory/f'{phase}-assessment.json').read_text(encoding='utf-8'))
        result.append({'phase':phase,'cleared':assessment['clearance'] is not None,
                       'findings':[(f.get('check_id',f.get('obligation',f.get('type'))),
                                    f.get('status',f.get('result',{}).get('status')),
                                    f.get('reason_code',f.get('result',{}).get('reason_code'))) for f in assessment['findings']]})
    return result


def execute(output_root=None):
    before = protected_hashes()
    now = datetime.now(timezone.utc)
    run_id = 'verification-loop-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    directory = (Path(output_root) if output_root else ROOT/'runs')/run_id
    directory.mkdir(parents=True,exist_ok=False)
    write_json(directory/'protected-inputs-before.json',before)
    summaries = []
    try:
        for shape in ('single','multi'):
            summaries.append(run_one(shape,directory/shape,f'{run_id}:{shape}'))
        semantic_parity = signatures(directory/'single')==signatures(directory/'multi')
        if not semantic_parity:
            raise AssertionError('ADAPTER_OBLIGATION_RESULTS_DIFFER')
        preservation = assert_preserved(before)
        sources = {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'procedural_loop').rglob('*'))
            if p.is_file() and p.suffix in {'.py','.json','.md'} and '__pycache__' not in p.parts}
        manifest = {'run_id':run_id,'status':'COMPLETE','mode':'offline_scripted_research',
            'started_at':now.isoformat(),'ended_at':datetime.now(timezone.utc).isoformat(),
            'python':platform.python_version(),'source_hashes':sources,'semantic_adapter_parity':semantic_parity,
            'preservation':preservation,'shapes':summaries,'model_calls':0,'network_calls':0,'spend_usd':'0',
            'limitations':['Synthetic replay with scripted host response; not live agents, real Claude support, or production enforcement.',
                           'Procedural eligibility only under explicit fixture policy; no model intelligence/trading quality claim.']}
        write_json(directory/'experiment.json',manifest)
        lines = ['# First complete offline verification loop','',f'Run: `{run_id}`. **COMPLETE**.',
            '', 'Authored fixture evidence procedure with scripted host response. No model calls, API spending or trade execution.',
            '', '| Shape | Initial | Expired reuse | After refresh | Old clearance rejected |',
            '|---|---|---|---|---|']
        for summary in summaries:
            phases=summary['phases']
            lines.append(f"| {summary['shape']} | {phases[0]['status']} | {phases[1]['status']} | {phases[2]['status']} | Yes |")
        lines += ['', 'Both shapes used the same semantic evidence and policy and produced equivalent obligation outcomes.',
            'The expired assessment remains recorded. Delivery, acknowledgement, refresh, new proposal and reassessment were executed during the run.',
            'A separate distorted-value control received no clearance.', '',
            f"Protected historical/budget inputs unchanged: {preservation['unchanged_files']}.", '',
            'Each shape directory contains complete proposal/assessment JSON, raw trace.jsonl, queryable trace.sqlite, console.log, summary and trace validation.',
            'The existing trace viewer can list these run directories; this is log visibility, not a frontend product integration.', '',
            'Limits: synthetic actors and timelines; declared fixture dependency scope; no actual framework interception, portfolio suitability or semantic completeness claim.']
        (directory/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print(f'\nVERIFICATION LOOP COMPLETE: {directory}',flush=True)
        return directory
    except BaseException as exc:
        write_json(directory/'failure.json',{'status':'ERROR','error_type':type(exc).__name__,'message':str(exc),
            'preservation':assert_preserved(before)})
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run');run.add_argument('--output-root',type=Path)
    inspect=sub.add_parser('inspect');inspect.add_argument('--run',type=Path,required=True)
    inspect.add_argument('--kind');inspect.add_argument('--limit',type=int,default=30)
    validate=sub.add_parser('validate');validate.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='run':execute(args.output_root)
    elif args.command=='validate':print(json.dumps(inspect_recording(args.run),indent=2))
    else:print(json.dumps(query(args.run,args.kind,args.limit),indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
