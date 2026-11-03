"""Thirty-minute paired observation with local analysis alongside inference."""
import argparse
import json
import random
import subprocess
import sys
import time
import uuid
from .analysis import analyze_session
from .experiment import terminate_research_child
from .runner import ROOT, CONFIG, upstream_check
from .trace import digest, utc


def schedule(duration=1800, cadence=600):
    if duration != 1800 or cadence != 600:
        raise ValueError('Approved window is 1800 seconds, checkpoints at 0/600/1200')
    return [0, 600, 1200]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--approve-paid', action='store_true')
    parser.add_argument('--approve-thirty-minute', action='store_true')
    parser.add_argument('--budget-usd', type=float, default=5)
    args = parser.parse_args()
    policy = json.loads((ROOT/'budget_policy.json').read_text())
    if not args.approve_paid or not args.approve_thirty_minute or args.budget_usd != policy['hard_limit_usd']:
        parser.error('Explicit 30-minute paid authorization and saved cumulative ceiling required')
    fixture = json.loads((ROOT/'fixtures/eth_synthetic_v1.json').read_text())
    config_hash = digest(dict(config=CONFIG, fixture=fixture))
    smoke_path = ROOT/'runs/paid-smoke-success.json'
    if not smoke_path.exists() or json.loads(smoke_path.read_text())['config_hash'] != config_hash:
        parser.error('Matching successful paid preflight required')
    if (ROOT/'STOP').exists():
        parser.error('STOP file exists')
    upstream_check()
    session = ROOT/'runs'/f"{time.strftime('%Y%m%d-%H%M%S')}-30min-{uuid.uuid4().hex[:6]}"
    session.mkdir(parents=True)
    frozen = session/'fixture.json'
    frozen.write_text(json.dumps(fixture,indent=2),encoding='utf-8')
    start = time.monotonic()
    end = start+1800
    deadline = time.time()+1800
    summary = dict(started_at=utc(), status='running', mode='paid', duration_seconds=1800,
                   planned_pair_offsets_seconds=schedule(), parallel_arms=True, config_hash=config_hash,
                   fixture_hash=digest(fixture), budget_policy=policy, pairs=[], phase='starting')
    active = {}
    next_analysis = 0
    def save():
        temporary = session/'experiment.tmp'
        temporary.write_text(json.dumps(summary,indent=2),encoding='utf-8')
        temporary.replace(session/'experiment.json')
    def tick(force=False):
        nonlocal next_analysis
        if (ROOT/'STOP').exists():
            raise InterruptedError('STOP file reached')
        if force or time.monotonic() >= next_analysis:
            summary['elapsed_seconds'] = round(time.monotonic()-start,1)
            save()
            analysis = analyze_session(session)
            print(f'ANALYSIS {utc()} runs={len(analysis["runs"])} completed={sum(r["status"]=="success" for r in analysis["runs"])}',flush=True)
            next_analysis = time.monotonic()+15
    save()
    print(f'VISIBLE 30-MINUTE SESSION: {session}',flush=True)
    print('Both model arms run concurrently at 0, 10 and 20 minutes. Same frozen synthetic fixture. Shared $5 cap. Local analysis every 15 seconds. STOP or Ctrl+C stops both trees.',flush=True)
    failed = False
    try:
        for index, offset in enumerate(schedule()):
            summary['phase']='waiting_checkpoint'
            while time.monotonic()<start+offset:
                tick()
                time.sleep(.2)
            if time.monotonic()>=end:
                raise TimeoutError('Observation deadline reached before checkpoint')
            order=['sol','terra']
            random.Random(index).shuffle(order)
            pair=dict(pair_id=f'{session.name}-pair-{index}', started_at=utc(), order=order, arms=[])
            summary['pairs'].append(pair)
            summary['phase']='running_pair'
            for arm in order:
                command=[sys.executable,'-u','-m','trustkernel.runner','--mode','paid',
                         '--arm',arm,'--model',f'gpt-6.1-{arm}','--fixture',str(frozen),
                         '--output',str(session),'--pair-id',pair['pair_id'],'--deadline',str(deadline),
                         '--approve-paid','--budget','5','--budget-db',str(ROOT/'runs/approved-budget.sqlite')]
                print('COMMAND: '+subprocess.list2cmdline(command),flush=True)
                active[arm]=(subprocess.Popen(command,cwd=ROOT),time.monotonic()+540)
            tick(True)
            while active:
                for arm,(process,arm_end) in list(active.items()):
                    status=process.poll()
                    if status is not None:
                        pair['arms'].append(dict(arm=arm,exit_code=status,ended_at=utc()))
                        del active[arm]
                        save()
                        if status:
                            raise RuntimeError(f'{arm} failed or budget stopped; ending both arms')
                    elif time.monotonic()>=min(arm_end,end):
                        raise TimeoutError(f'{arm} child deadline reached')
                tick()
                time.sleep(.1)
            pair['ended_at']=utc()
            tick(True)
        summary['phase']='observation_tail'
        while time.monotonic()<end:
            tick()
            time.sleep(.2)
        summary['status']='success'
    except (Exception,KeyboardInterrupt) as exc:
        failed=True
        summary.update(status='stopped_or_failed',error=f'{type(exc).__name__}: {exc}')
        print(summary['error'],flush=True)
    finally:
        for process,_ in active.values():
            terminate_research_child(process)
        summary.update(ended_at=utc(),elapsed_seconds=round(time.monotonic()-start,1),phase='finished')
        save()
        analyze_session(session)
    print(f'30-MINUTE WINDOW {summary["status"]}: {session}',flush=True)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
