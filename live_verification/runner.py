"""Create a new offline live-ledger -> scoped-rules run, without research calls."""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .preservation import ROOT, verify as verify_preserved

DEFAULT_SOURCE = ROOT / 'runs/20261102T192912Z-live-30min-2f24b1'


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def offline_guard(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.exec'}:
        raise RuntimeError('OFFLINE_VERIFICATION_DENIES_NETWORK_OR_SUBPROCESS:' + event)


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def audit_ledger_index(folder):
    """Independent canonical/index/ref check, outside the builder validator."""
    rows = read_rows(folder / 'ledger.jsonl')
    assert len({r['id'] for r in rows}) == len(rows), 'Duplicate canonical row ID'
    ids = {r['id'] for r in rows}
    for row in rows:
        for ref in row.get('refs', []):
            assert ref in ids, 'Unresolved declared foreign key:' + ref
    db = sqlite3.connect((folder / 'ledger.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        saved = db.execute('SELECT id,row_json FROM records').fetchall()
        assert len(saved) == len(rows)
        assert {i: json.loads(j) for i, j in saved} == {r['id']: r for r in rows}
    finally:
        db.close()
    return {'status': 'PASS', 'canonical_rows': len(rows), 'exact_sqlite_logical_parity': True,
            'all_declared_refs_resolve': True}


def run(source):
    source = source.resolve()
    if not source.is_relative_to((ROOT / 'runs').resolve()):
        raise ValueError('SOURCE_MUST_BE_A_PRESERVED_PROJECT_RUN')
    metadata = json.loads((source / 'experiment.json').read_text(encoding='utf-8'))
    if metadata.get('status') != 'success' or metadata.get('source_mode') != 'live_native':
        raise ValueError('SOURCE_MUST_BE_A_CLOSED_SUCCESSFUL_NATIVE_LIVE_RECORDING')
    if (source / 'fixture.json').exists():
        raise ValueError('SYNTHETIC_FIXTURE_IS_NOT_THE_REQUESTED_LIVE_CORPUS')
    before = verify_preserved()
    sys.addaudithook(offline_guard)
    from .ledger import build_ledger, validate_ledger
    from .rules import assess_ledger, validate_assessment
    name = 'live-verification-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    output = ROOT / 'runs' / name
    output.mkdir(exist_ok=False)
    state = {'status': 'running', 'source_session': str(source), 'started_at': datetime.now(timezone.utc).isoformat(),
             'mode': 'offline_ledger_and_scoped_rules', 'new_model_calls': 0, 'new_source_requests': 0,
             'budget_mutation_authorized': False, 'output': str(output),
             'implementation_hashes': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.rglob('*'))
                if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py', '.md', '.json'}}}
    dump(output / 'experiment.json', state)
    try:
        print('BUILD LEDGER', flush=True)
        manifest = build_ledger(source, output / 'ledger')
        print('VALIDATE LEDGER', flush=True)
        validation = validate_ledger(output / 'ledger', source)
        independent = audit_ledger_index(output / 'ledger')
        print('ASSESS RULES', flush=True)
        assessment = assess_ledger(output / 'ledger', output / 'findings')
        assessment_validation = validate_assessment(output / 'findings', output / 'ledger')
        print('REPRODUCE CANONICAL LEDGER', flush=True)
        repeat = build_ledger(source, output / 'reproducibility-ledger')
        validate_ledger(output / 'reproducibility-ledger', source)
        original_bytes = (output / 'ledger/ledger.jsonl').read_bytes()
        repeat_bytes = (output / 'reproducibility-ledger/ledger.jsonl').read_bytes()
        if original_bytes != repeat_bytes:
            raise ValueError('CANONICAL_LEDGER_REBUILD_IS_NOT_IDENTICAL')
        if manifest['build_id'] != repeat['build_id']:
            raise ValueError('REPEATED_BUILD_ID_CHANGED')
        print('REPRODUCE SCOPED FINDINGS', flush=True)
        assess_ledger(output / 'reproducibility-ledger', output / 'reproducibility-findings')
        validate_assessment(output / 'reproducibility-findings', output / 'reproducibility-ledger')
        finding_bytes = (output / 'findings/findings.jsonl').read_bytes()
        if finding_bytes != (output / 'reproducibility-findings/findings.jsonl').read_bytes():
            raise ValueError('SCOPED_FINDING_REBUILD_IS_NOT_IDENTICAL')
        for relative, expected in state['implementation_hashes'].items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
                raise ValueError('VERIFICATION_IMPLEMENTATION_CHANGED_DURING_RUN:' + relative)
        state.update(status='success', ledger_manifest=manifest, ledger_validation=validation,
                     independent_ledger_audit=independent, assessment=assessment, assessment_validation=assessment_validation,
                     reproducibility={'status': 'PASS', 'canonical_byte_identical': True,
                                      'build_id': manifest['build_id'],
                                      'canonical_sha256': hashlib.sha256(original_bytes).hexdigest(),
                                      'findings_byte_identical': True,
                                      'findings_sha256': hashlib.sha256(finding_bytes).hexdigest()},
                     preservation=verify_preserved())
    except Exception as exc:
        state.update(status='failed', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        try:
            state['preservation'] = verify_preserved()
        except Exception as exc:
            state['status'] = 'failed'
            state['preservation'] = {'status': 'ERROR', 'message': str(exc)}
        state['ended_at'] = datetime.now(timezone.utc).isoformat()
        dump(output / 'experiment.json', state)
    if state['status'] != 'success':
        raise RuntimeError('OFFLINE_VERIFICATION_FAILED_PRESERVATION_GATE:' + str(output))
    print(json.dumps({'status': state['status'], 'output': str(output),
                      'build_id': manifest['build_id'], 'rows': independent['canonical_rows']}, indent=2), flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    run(args.source)


if __name__ == '__main__':
    main()
