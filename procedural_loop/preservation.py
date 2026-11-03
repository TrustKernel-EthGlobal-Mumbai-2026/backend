"""Guard the frozen research corpus and original spending ledger without mutation."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def protected_hashes():
    manifest = ROOT/'explorations/rules/contract-v0.2/assessments/assessment-cba74a3938fc4d5f840d3765/manifest.json'
    captured = json.loads(manifest.read_text(encoding='utf-8'))['source_hashes']
    result = {}
    for name, expected in captured.items():
        actual = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('PROTECTED_HISTORICAL_INPUT_CHANGED:'+name)
        result[name] = actual
    for name in ('runs/approved-budget.sqlite', 'budget_policy.json'):
        result[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return result


def assert_preserved(before):
    after = protected_hashes()
    if before != after:
        raise ValueError('PROTECTED_INPUT_CHANGED_DURING_LOOP')
    return {'status':'PASS','unchanged_files':len(after)}
