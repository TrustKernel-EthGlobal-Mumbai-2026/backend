"""Approved paired live-source 30-minute paper-research supervisor."""
import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from trustkernel.experiment import terminate_research_child
from trustkernel.runner import ROOT,upstream_check
from trustkernel.trace import utc
from .preservation import historical_hashes,budget_snapshot,assert_preserved

OFFSETS=(0,600,1200)
DURATION=1800


def implementation_hashes():
    package=ROOT/'live_experiment'
    paths=list(package.glob('*.py'))+list(package.glob('*.md'))+list((package/'tests').glob('*.py'))
    return {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def validate_preflight(path):
    report=json.loads(Path(path).read_text(encoding='utf-8'))
    ended=datetime.fromisoformat(report['ended_at'])
    age=(datetime.now(timezone.utc)-ended).total_seconds()
    if report.get('status')!='PASS' or report.get('core_ready') is not True or report.get('model_calls')!=0:
        raise PermissionError('Core live data-only preflight must pass before paid inference')
    if not 0<=age<=300:raise PermissionError('Live-source preflight must be less than five minutes old')
    if report['as_of']!=datetime.now().date().isoformat():
        raise PermissionError('Native local analysis date differs from the source preflight')
    for name in ('get_stock_data','get_verified_market_snapshot'):
        item=report['providers'][name]
        if item['status']!='AVAILABLE' or not item.get('content'):
            raise PermissionError('Required native live source unavailable: '+name)
    urls=[e['payload'].get('url','') for e in report.get('events',[]) if e.get('kind')=='source.http.end' and e['payload'].get('status')==200]
    if not any(urlsplit(url).hostname in {'query1.finance.yahoo.com','query2.finance.yahoo.com'}
               and urlsplit(url).scheme=='https' and urlsplit(url).path.startswith('/v8/finance/chart/') for url in urls):
        raise PermissionError('Fresh live Yahoo chart HTTP witness missing from preflight')
    return report


def atomic_json(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    temporary.replace(path)


class EventMonitor:
    def __init__(self):self.positions={}

    def poll(self,session):
        for path in session.glob('*/trace.jsonl'):
            start=self.positions.get(str(path),0)
            with path.open('rb') as handle:
                handle.seek(start);data=handle.read()
            end=data.rfind(b'\n')
            if end<0:continue
            chunk=data[:end+1]
            self.positions[str(path)]=start+len(chunk)
            for line in chunk.splitlines():
                event=json.loads(line);kind=event['kind'];p=event.get('payload',{})
                if kind=='budget.hard_stop':raise PermissionError('Shared cumulative budget hard stop reached')
                if kind=='run.error':raise RuntimeError('A live research arm recorded '+str(p.get('error_type','an error')))
                if kind=='evidence.retrieved' and p.get('tool') in ('get_stock_data','get_verified_market_snapshot'):
                    if p.get('source_status') not in ('AVAILABLE',):
                        raise RuntimeError('Core native source became unavailable: '+str(p.get('tool'))+'/'+str(p.get('source_status')))
                if kind=='source.tool.error' and p.get('tool') in ('get_stock_data','get_verified_market_snapshot'):
                    raise RuntimeError('Core native source raised an error: '+str(p.get('tool')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-paid',action='store_true')
    parser.add_argument('--approve-thirty-minute',action='store_true')
    parser.add_argument('--budget-usd',type=float,default=5)
    parser.add_argument('--preflight',type=Path,required=True)
    args=parser.parse_args()
    if not args.approve_paid or not args.approve_thirty_minute or args.budget_usd!=5:
        parser.error('Explicit live 30-minute authorization and unchanged cumulative $5 ceiling required')
    if (ROOT/'STOP').exists():parser.error('STOP file exists; no paid run started')
    if not os.environ.get('OPENAI_API_KEY'):parser.error('OPENAI_API_KEY missing; no paid run started')
    preflight=validate_preflight(args.preflight)
    upstream_check()
    before_hashes=historical_hashes();before_budget=budget_snapshot()
    if before_budget['hard_limit_usd']!=5 or not math.isfinite(before_budget['committed_plus_holds_usd']):
        parser.error('Existing cumulative budget policy/state is invalid')
    # Reserve enough headroom for the first concurrent requests before starting.
    if before_budget['committed_plus_holds_usd']+0.48072>5:
        parser.error('Insufficient remaining conservative budget for initial paired requests')
    lock=ROOT/'runs/.live-window.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:parser.error('A live-window lock exists; no duplicate run started')
    os.write(fd,json.dumps({'pid':os.getpid(),'started_at':utc()}).encode());os.close(fd)
    session=ROOT/'runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-live-30min-'+uuid4().hex[:6])
    session.mkdir(parents=True,exist_ok=False)
    atomic_json(session/'source-preflight.json',preflight)
    atomic_json(session/'protected-inputs-before.json',before_hashes)
    atomic_json(session/'budget-before.json',before_budget)
    code_hashes=implementation_hashes()
    start=time.monotonic();end=start+DURATION;deadline=time.time()+DURATION
    summary={'status':'running','source_mode':'live_native','mode':'paid_live_native_sources',
        'started_at':utc(),'duration_seconds':DURATION,'planned_pair_offsets_seconds':list(OFFSETS),
        'parallel_arms':True,'first_pair_is_paid_smoke':True,'deadline_epoch':deadline,
        'budget_usd':5,'budget_scope':'Cumulative including all prior project charges and unknown holds',
        'budget_before_committed_plus_holds_usd':before_budget['committed_plus_holds_usd'],
        'source_preflight_path':str(args.preflight),'source_preflight_sha256':hashlib.sha256(args.preflight.read_bytes()).hexdigest(),
        'implementation_hashes':code_hashes,'pairs':[],'phase':'starting',
        'limits':['Live evidence may differ across arms by request/timing; not identical fixture replay.',
            'No forced tool invocation, TrustKernel intervention, trading or model intelligence ranking.',
            'Native source gaps and daily/partial bar timestamps remain explicit.']}
    active={};monitor=EventMonitor();next_analysis=0;failed=False

    def save():
        summary['elapsed_seconds']=round(time.monotonic()-start,1)
        atomic_json(session/'experiment.json',summary)
        atomic_json(ROOT/'runs/live-current.json',{'session':str(session),'status':summary['status'],
            'started_at':summary['started_at'],'pid':os.getpid(),'deadline_epoch':deadline})

    def tick(force=False):
        nonlocal next_analysis
        if (ROOT/'STOP').exists():raise InterruptedError('STOP file reached')
        monitor.poll(session)
        if force or time.monotonic()>=next_analysis:
            if implementation_hashes()!=code_hashes:raise RuntimeError('Live experiment implementation changed during run')
            save()
            from .review import analyze_session
            analysis=analyze_session(session)
            print('LIVE ANALYSIS '+utc()+f" runs={len(analysis.get('runs',[]))} elapsed={summary['elapsed_seconds']}s",flush=True)
            next_analysis=time.monotonic()+15

    save()
    print('VISIBLE LIVE 30-MINUTE SESSION: '+str(session),flush=True)
    print('Native live source results. Parallel Sol/Terra at0/10/20minutes; same cumulative$5cap; no trade authority.',flush=True)
    try:
        for index,offset in enumerate(OFFSETS):
            summary['phase']='waiting_checkpoint'
            while time.monotonic()<start+offset:
                tick();time.sleep(.2)
            if time.monotonic()>=end:raise TimeoutError('Overall deadline before checkpoint')
            pair={'pair_id':f'{session.name}-pair-{index}','started_at':utc(),'arms':[]}
            order=['sol','terra'];random.Random(index).shuffle(order);pair['order']=order
            summary['pairs'].append(pair);summary['phase']='running_pair'
            for arm in order:
                command=[sys.executable,'-B','-u','-X','utf8','-m','live_experiment.arm',
                    '--arm',arm,'--model','gpt-6.1-'+arm,'--output',str(session),'--pair-id',pair['pair_id'],
                    '--deadline',str(deadline),'--approve-paid','--budget','5',
                    '--budget-db',str(ROOT/'runs/approved-budget.sqlite')]
                print('COMMAND: '+subprocess.list2cmdline(command),flush=True)
                active[arm]=(subprocess.Popen(command,cwd=ROOT),time.monotonic()+540)
            tick(True)
            while active:
                for arm,(process,arm_end) in list(active.items()):
                    status=process.poll()
                    if status is not None:
                        pair['arms'].append({'arm':arm,'exit_code':status,'ended_at':utc()})
                        del active[arm];save()
                        if status:raise RuntimeError(arm+' failed; stop both arms without retry/substitution')
                    elif time.monotonic()>=min(arm_end,end):
                        raise TimeoutError(arm+' child deadline reached')
                tick();time.sleep(.1)
            pair['ended_at']=utc();tick(True)
        summary['phase']='observation_tail'
        while time.monotonic()<end:
            tick();time.sleep(.2)
        summary['status']='success'
    except (Exception,KeyboardInterrupt) as exc:
        failed=True;summary.update(status='stopped_or_failed',error=f'{type(exc).__name__}: {exc}')
        print(summary['error'],flush=True)
    finally:
        for process,_ in active.values():terminate_research_child(process)
        summary.update(ended_at=utc(),phase='finished')
        try:summary['preservation']=assert_preserved(before_hashes,before_budget)
        except Exception as exc:
            failed=True;summary.update(status='stopped_or_failed',preservation_error=f'{type(exc).__name__}: {exc}')
        summary['budget_after']=budget_snapshot()
        save()
        try:
            from .review import analyze_session
            analyze_session(session)
        finally:
            if lock.exists() and json.loads(lock.read_text()).get('pid')==os.getpid():lock.unlink()
    print('LIVE WINDOW '+summary['status']+': '+str(session),flush=True)
    raise SystemExit(1 if failed else 0)


if __name__=='__main__':main()
