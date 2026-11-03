"""Observable offline loop events; no credentials, framework imports or network."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


class Recorder:
    """Compatible event index columns for the existing local trace viewer."""

    def __init__(self, directory, run_id):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.run_id = run_id
        self.seq = 0
        self.previous_hash = None
        self.raw = (self.directory / 'trace.jsonl').open('x', encoding='utf-8', newline='\n')
        self.console = (self.directory / 'console.log').open('x', encoding='utf-8', newline='\n')
        self.db = sqlite3.connect(self.directory / 'trace.sqlite')
        self.db.execute('''CREATE TABLE events (
            seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE, run_id TEXT, timestamp TEXT,
            kind TEXT, span_id TEXT, parent_id TEXT, payload_json TEXT, event_hash TEXT)''')
        self.db.execute('CREATE INDEX events_kind ON events(kind)')
        self.db.commit()

    def emit(self, kind, payload, *, as_of=None):
        # Only authored synthetic fixture content and local findings are accepted by the runner.
        # Evidence valid time is in payload, separate from this execution observation timestamp.
        self.seq += 1
        event = dict(schema_version='procedural-loop-trace-0.1', seq=self.seq,
                     event_id=f'{self.run_id}:{self.seq}', run_id=self.run_id, timestamp=utc(),
                     kind=kind, span_id=None, parent_id=None,
                     context={'mode':'offline_scripted_research', 'scenario_as_of':as_of},
                     payload=payload, previous_hash=self.previous_hash)
        event['event_hash'] = digest(event)
        self.raw.write(canonical(event)+'\n')
        self.raw.flush()
        self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)', (
            event['seq'], event['event_id'], self.run_id, event['timestamp'], kind, None, None,
            canonical(payload), event['event_hash']))
        self.db.commit()
        self.previous_hash = event['event_hash']
        line = f"#{self.seq:03d} [{self.run_id}] {kind}"
        if isinstance(payload,dict) and 'status' in payload:
            line += f" | {payload['status']}"
        if isinstance(payload,dict):
            label = payload.get('obligation') or payload.get('reason_code')
            if label:
                line += ' | '+str(label)[:160]
        print(line, flush=True)
        self.console.write(line+'\n')
        self.console.flush()
        return event

    def close(self):
        self.raw.close()
        self.console.close()
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def inspect_recording(directory):
    """Read-only hash-chain, dense-prefix and full logical JSONL/index parity audit."""
    directory = Path(directory).resolve()
    events = [json.loads(line) for line in (directory/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    previous = None
    for i, event in enumerate(events,1):
        body = dict(event)
        identity = body.pop('event_hash')
        if event['seq'] != i or event['previous_hash'] != previous or digest(body) != identity:
            raise ValueError('TRACE_CHAIN_OR_SEQUENCE_MISMATCH')
        previous = identity
    db = sqlite3.connect((directory/'trace.sqlite').as_uri()+'?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        indexed = db.execute('SELECT seq,event_id,run_id,timestamp,kind,span_id,parent_id,payload_json,event_hash FROM events ORDER BY seq').fetchall()
        expected = [(e['seq'],e['event_id'],e['run_id'],e['timestamp'],e['kind'],e['span_id'],e['parent_id'],canonical(e['payload']),e['event_hash']) for e in events]
        if indexed != expected:
            raise ValueError('TRACE_INDEX_PARITY_MISMATCH')
    finally:
        db.close()
    return {'status':'PASS','events':len(events),'last_event_hash':previous,'index_parity':True}


def query(directory, kind=None, limit=30):
    directory = Path(directory).resolve()
    db = sqlite3.connect((directory/'trace.sqlite').as_uri()+'?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        rows = db.execute('SELECT seq,kind,payload_json FROM events WHERE (? IS NULL OR kind=?) ORDER BY seq LIMIT ?', (kind,kind,limit)).fetchall()
        return [dict(seq=r[0],kind=r[1],payload=json.loads(r[2])) for r in rows]
    finally:
        db.close()
