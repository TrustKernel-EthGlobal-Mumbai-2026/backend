"""Preserve prior experiments while allowing only authorized budget appends."""
import hashlib
import json
import sqlite3
from pathlib import Path

from recorded_loop.preservation import ROOT,capture as capture_prior

RECORDED=ROOT/'runs/recorded-verification-20261102T182919Z-8ad6c261'
BUDGET_PATH='runs/approved-budget.sqlite'


def historical_hashes():
    values=capture_prior()
    values.pop(BUDGET_PATH,None)
    manifest=json.loads((RECORDED/'experiment.json').read_text(encoding='utf-8'))
    for path,expected in manifest['source_hashes'].items():
        actual=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('RECORDED_REPLAY_CODE_CHANGED:'+path)
        values[path]=actual
    for path in sorted(RECORDED.rglob('*')):
        if path.is_file():values[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
    launcher=ROOT/'Run-Recorded-Verification.ps1'
    values[str(launcher.relative_to(ROOT))]=hashlib.sha256(launcher.read_bytes()).hexdigest()
    return values


def budget_snapshot():
    path=ROOT/BUDGET_PATH
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    try:
        db.execute('PRAGMA query_only=ON')
        total=db.execute('SELECT reserved FROM budget WHERE id=1').fetchone()[0]
        policy=db.execute('SELECT initial_limit,active_limit,hard_limit FROM budget_policy WHERE id=1').fetchone()
        rows=db.execute('SELECT id,reserved,charge,status,response_id FROM requests ORDER BY id').fetchall()
    finally:db.close()
    return {'committed_plus_holds_usd':total,'initial_limit_usd':policy[0],
        'active_limit_usd':policy[1],'hard_limit_usd':policy[2],
        'requests':{r[0]:{'reserved':r[1],'charge':r[2],'status':r[3],'response_id':r[4]} for r in rows}}


def assert_preserved(before_hashes,before_budget):
    after_hashes=historical_hashes()
    if before_hashes!=after_hashes:raise ValueError('HISTORICAL_EXPERIMENT_ASSET_CHANGED')
    after=budget_snapshot()
    if (after['initial_limit_usd'],after['hard_limit_usd'])!=(3.0,5.0):
        raise ValueError('BUDGET_POLICY_CHANGED')
    if not 0<=after['committed_plus_holds_usd']<=5.0+1e-8:
        raise ValueError('BUDGET_CEILING_VIOLATED')
    for identity,row in before_budget['requests'].items():
        if after['requests'].get(identity)!=row:
            raise ValueError('PRIOR_BUDGET_REQUEST_OR_UNKNOWN_HOLD_CHANGED')
    new={k:v for k,v in after['requests'].items() if k not in before_budget['requests']}
    return {'status':'PASS','historical_files_unchanged':len(before_hashes),
        'prior_request_rows_unchanged':len(before_budget['requests']),'new_request_rows':len(new),
        'budget_exception':'Authorized new request reservations/settlements only; original rows and unknown holds immutable.',
        'committed_plus_holds_usd':after['committed_plus_holds_usd'],'hard_limit_usd':5.0}
