"""Inspect an existing derived ledger/findings run. Read-only, no model/network."""
import argparse
import json
import sqlite3
from pathlib import Path


def connect(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    return db


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--view', choices=['summary', 'findings', 'row', 'chain'], default='summary')
    p.add_argument('--rule')
    p.add_argument('--status', choices=['PASS', 'FAIL', 'INCONCLUSIVE', 'ERROR', 'NOT_APPLICABLE'])
    p.add_argument('--id')
    p.add_argument('--limit', type=int, default=12)
    a = p.parse_args()
    if not 1 <= a.limit <= 100:
        p.error('--limit must be between 1 and 100')
    if a.view == 'summary':
        result = {'coverage': json.loads((a.run/'ledger/coverage.json').read_text('utf-8')),
                  'findings': json.loads((a.run/'findings/summary.json').read_text('utf-8'))}
    elif a.view == 'findings':
        db = connect(a.run/'findings/findings.sqlite')
        try:
            selected = db.execute('SELECT row_json FROM findings WHERE (? IS NULL OR rule_id=?) AND (? IS NULL OR status=?) ORDER BY rule_id,run_id,finding_id LIMIT ?',
                                  (a.rule, a.rule, a.status, a.status, a.limit)).fetchall()
            result = [{k: row[k] for k in ['finding_id', 'rule_id', 'status', 'run_id', 'reason_code', 'observed', 'scope']}
                      for row in (json.loads(x[0]) for x in selected)]
        finally:
            db.close()
    else:
        if not a.id:
            p.error('--id required for row/chain views')
        ledger = connect(a.run/'ledger/ledger.sqlite')
        findings = connect(a.run/'findings/findings.sqlite')
        try:
            value = ledger.execute('SELECT row_json FROM records WHERE id=?', (a.id,)).fetchone()
            if value is None:
                value = findings.execute('SELECT row_json FROM findings WHERE finding_id=?', (a.id,)).fetchone()
            if value is None:
                p.error('Unknown canonical row/finding ID')
            result = json.loads(value[0])
            if a.view == 'chain':
                refs = result.get('source_refs', []) + result.get('candidate_refs', []) + result.get('span_refs', [])
                parents = {}
                for ref in refs:
                    raw = ledger.execute('SELECT row_json FROM records WHERE id=?', (ref['id'],)).fetchone()
                    if raw:
                        row = json.loads(raw[0])
                        parents[row['id']] = {k: row[k] for k in ['id', 'table', 'run_id', 'seq', 'kind', 'pointer', 'artifact_id', 'event_id', 'call_id', 'text_id', 'sha256', 'refs'] if k in row}
                result = {'finding': result, 'canonical_parent_index': list(parents.values()),
                          'note': 'Use row view with any ID for full stored context. References establish recorded provenance, not private reliance.'}
        finally:
            ledger.close(); findings.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
