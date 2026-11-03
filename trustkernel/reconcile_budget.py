"""One auditable migration of legacy permanent holds; no reset or limit increase."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from .billing import message_usage, upper_charge
from .trace import digest, utc


def reconcile(base):
    base = Path(base)
    ledger = base / 'approved-budget.sqlite'
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS reconciliation (id INTEGER PRIMARY KEY CHECK(id=1), audit_json TEXT)')
        existing = db.execute('SELECT audit_json FROM reconciliation WHERE id=1').fetchone()
        if existing:
            return json.loads(existing[0])
    rows, seen = [], set()
    for path in sorted(base.glob('*/*/trace.jsonl')):
        events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        if not events or events[0]['context'].get('mode') != 'paid':
            continue
        previous = None
        for event in events:
            copy = dict(event)
            saved = copy.pop('event_hash')
            if digest(copy) != saved or copy['previous_hash'] != previous:
                raise ValueError(f'Invalid trace chain: {path}')
            previous = saved
        usages = message_usage([e['payload'] for e in events])
        ends = {e['span_id']: e for e in events if e['kind'] == 'llm.end'}
        active_span = None
        for event in events:
            if event['kind'] == 'llm.start':
                active_span = event['span_id']
            if event['kind'] != 'budget.reserved':
                continue
            if event['payload'].get('request_id'):
                raise ValueError('New accounting already in use; legacy migration must run first')
            held = event['payload']['reserved_usd']
            end = ends.get(active_span)
            charge, response_id = held, None
            if end:
                message = end['payload']['response']['generations'][0][0]['message']
                response_id = message.get('response_metadata', {}).get('id') or message.get('id')
                if response_id in usages:
                    if response_id in seen:
                        raise ValueError('Duplicate provider response identity')
                    seen.add(response_id)
                    charge = upper_charge(event['context']['model'], usages[response_id])
                    if charge > held:
                        raise ValueError('Legacy hold insufficient for conservative usage; refusing automatic release')
            rows.append(dict(trace=str(path), reservation_event_hash=event['event_hash'],
                             completion_event_hash=end['event_hash'] if end else None,
                             response_id=response_id, held_usd=held, committed_upper_usd=charge))
    held = sum(r['held_usd'] for r in rows)
    charged = sum(r['committed_upper_usd'] for r in rows)
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT reserved FROM budget WHERE id=1').fetchone()[0]
        if abs(current-held) > .0000001:
            raise ValueError('Legacy trace reservations do not reconcile to ledger; no change made')
        audit = dict(timestamp=utc(), previous_reserved_usd=current, committed_upper_usd=charged,
                     released_unused_usd=current-charged, requests=len(rows), rows=rows,
                     method='Verified hash chains and provider token usage; highest cache-write rate on all input tokens; unknown usage retains full hold. Limits unchanged.')
        db.execute('UPDATE budget SET reserved=? WHERE id=1', (charged,))
        db.execute('INSERT INTO reconciliation VALUES (1,?)', (json.dumps(audit),))
    (base / 'budget-reconciliation.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    return audit


if __name__ == '__main__':
    from .runner import ROOT
    result = reconcile(ROOT / 'runs')
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'}, indent=2))
