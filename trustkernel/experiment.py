"""Visible supervisor. Offline default; paid and prolonged runs need explicit flags."""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path
from .runner import CONFIG, ROOT, upstream_check
from .trace import digest, utc


def terminate_research_child(process):
    """Windows venv redirectors can have an interpreter child; stop the tree."""
    if process.poll() is not None:
        return
    if os.name == 'nt':
        result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                capture_output=True, text=True)
        if result.returncode and process.poll() is None:
            raise RuntimeError('Could not stop research process tree; inspect child PID immediately')
    else:
        process.kill()
    process.wait(timeout=10)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['offline', 'paid'], default='offline')
    p.add_argument('--hours', type=float, default=0)
    p.add_argument('--interval-seconds', type=int, default=1800)
    p.add_argument('--budget-usd', type=float, default=0)
    p.add_argument('--approve-paid', action='store_true')
    p.add_argument('--approve-three-hour', action='store_true')
    p.add_argument('--fixture', type=Path, default=ROOT / 'fixtures/eth_synthetic_v1.json')
    args = p.parse_args()
    if args.hours not in (0, 3) or args.interval_seconds < 60:
        p.error('Only one-pair smoke or three-hour window supported; interval >=60 seconds')
    if args.mode == 'offline' and args.hours:
        p.error('Offline is short smoke only')
    if args.mode == 'paid' and (not args.approve_paid or not math.isfinite(args.budget_usd) or args.budget_usd <= 0):
        p.error('Paid run needs --approve-paid and --budget-usd')
    policy = None
    if args.mode == 'paid':
        policy = json.loads((ROOT / 'budget_policy.json').read_text(encoding='utf-8'))
        if args.budget_usd != policy['hard_limit_usd']:
            p.error('Use the saved authorized hard ceiling; no automatic budget reset or increase')
    fixture = json.loads(args.fixture.read_text(encoding='utf-8'))
    config_hash = digest(dict(config=CONFIG, fixture=fixture))
    if args.hours:
        smoke = ROOT / 'runs/paid-smoke-success.json'
        if not args.approve_three_hour or not smoke.exists() or json.loads(smoke.read_text())['config_hash'] != config_hash:
            p.error('Three-hour run needs explicit approval and matching successful paid smoke')
    upstream_check()
    if (ROOT / 'STOP').exists():
        p.error('STOP file exists; inspect it before manually removing')
    session = ROOT / 'runs' / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    session.mkdir(parents=True)
    frozen = session / 'fixture.json'
    frozen.write_text(json.dumps(fixture, indent=2), encoding='utf-8')
    deadline = time.time() + (10800 if args.hours else (600 if args.mode == 'paid' else 120))
    summary = dict(started_at=utc(), mode=args.mode, hours=args.hours, config_hash=config_hash,
                   fixture_hash=digest(fixture), budget_usd=args.budget_usd, pairs=[], status='running')
    if policy:
        summary['budget_policy'] = policy
        summary['budget_ledger'] = str(ROOT / 'runs/approved-budget.sqlite')
    def save():
        (session / 'experiment.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    save()
    print(f'VISIBLE SESSION: {session}', flush=True)
    print('Offline outputs are SCRIPTED; paid outputs are real inference. Ctrl+C or create STOP to stop.', flush=True)
    failed = False
    process = None
    start = time.monotonic()
    pair_count = 6 if args.hours else 1
    try:
        for pair_index in range(pair_count):
            scheduled = start + pair_index * args.interval_seconds
            while time.monotonic() < scheduled:
                if time.time() >= deadline or (ROOT / 'STOP').exists():
                    raise TimeoutError('Deadline/STOP reached')
                time.sleep(min(1, scheduled - time.monotonic()))
            order = ['sol', 'terra']
            random.Random(pair_index).shuffle(order)
            pair = dict(pair_id=f'{session.name}-pair-{pair_index}', order=order, arms=[])
            summary['pairs'].append(pair)
            for arm in order:
                if time.time() >= deadline or (ROOT / 'STOP').exists():
                    raise TimeoutError('Deadline/STOP reached')
                command = [sys.executable, '-u', '-m', 'trustkernel.runner', '--mode', args.mode,
                           '--arm', arm, '--model', f'gpt-6.1-{arm}', '--fixture', str(frozen),
                           '--output', str(session), '--pair-id', pair['pair_id'], '--deadline', str(deadline)]
                if args.mode == 'paid':
                    command += ['--approve-paid', '--budget', str(args.budget_usd), '--budget-db', str(ROOT / 'runs/approved-budget.sqlite')]
                print('COMMAND: ' + subprocess.list2cmdline(command), flush=True)
                process = subprocess.Popen(command, cwd=ROOT)
                arm_deadline = min(deadline, time.time() + (300 if args.mode == 'paid' else 60))
                while process.poll() is None:
                    if time.time() >= arm_deadline or (ROOT / 'STOP').exists():
                        terminate_research_child(process)
                        raise TimeoutError('Child wall-clock bound/STOP reached')
                    time.sleep(.1)
                pair['arms'].append(dict(arm=arm, exit_code=process.returncode))
                save()
                if process.returncode:
                    failed = True
                    raise RuntimeError(f'{arm} failed; no silent substitution or further spending')
        summary['status'] = 'success'
        if args.mode == 'paid' and not args.hours:
            (ROOT / 'runs/paid-smoke-success.json').write_text(json.dumps(dict(config_hash=config_hash, session=str(session), verified_at=utc())), encoding='utf-8')
    except (Exception, KeyboardInterrupt) as exc:
        failed = True
        summary.update(status='stopped_or_failed', error=f'{type(exc).__name__}: {exc}')
        print(summary['error'], flush=True)
    finally:
        if process is not None and process.poll() is None:
            terminate_research_child(process)
        summary['ended_at'] = utc()
        save()
    print(f"EXPERIMENT {summary['status']}: {session}", flush=True)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
