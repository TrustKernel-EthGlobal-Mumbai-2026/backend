"""Independent read-only integrity audit of six original framework recordings."""
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SESSION=ROOT/'runs/20261030-010033-30min-597a75'


def audit_sources():
    results=[]
    for path in sorted(SESSION.glob('*/trace.jsonl')):
        raw=path.read_bytes()
        events=[json.loads(line) for line in raw.splitlines()]
        previous=None
        for seq,event in enumerate(events,1):
            body=dict(event);identity=body.pop('event_hash')
            expected=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            if event['seq']!=seq or event['previous_hash']!=previous or expected!=identity:
                raise ValueError('ORIGINAL_SOURCE_HASHCHAIN_MISMATCH:'+str(path))
            previous=identity
        db=sqlite3.connect(path.with_suffix('.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            rows=db.execute('SELECT seq,event_id,run_id,timestamp,kind,span_id,parent_id,payload_json,event_hash FROM events ORDER BY seq').fetchall()
            actual=[(r[0],r[1],r[2],r[3],r[4],r[5],r[6],json.loads(r[7]),r[8]) for r in rows]
            expected=[(e['seq'],e['event_id'],e['run_id'],e['timestamp'],e['kind'],e['span_id'],e['parent_id'],e['payload'],e['event_hash']) for e in events]
            if actual!=expected:raise ValueError('ORIGINAL_SOURCE_INDEX_PARITY_MISMATCH:'+str(path))
        finally:db.close()
        counts=Counter(e['kind'] for e in events)
        starts=next(e for e in events if e['kind']=='run.start')
        ends=events[-1]
        if ends['kind']!='run.end' or ends['payload']['status']!='success':
            raise ValueError('SOURCE_RUN_NOT_SUCCESSFULLY_TERMINATED:'+str(path))
        results.append({'run_id':events[0]['run_id'],'path':str(path.relative_to(ROOT)).replace('\\','/'),
            'sha256':hashlib.sha256(raw).hexdigest(),'events':len(events),'status':'PASS',
            'index_parity':True,'counts':dict(counts),'model':starts['context']['model'],
            'effort':starts['context']['effort'],'trustkernel_feedback':starts['payload']['config']['trustkernel_feedback'],
            'started_at':starts['timestamp'],'ended_at':ends['timestamp'],
            'evidence_kind':'frozen_synthetic_fixture','private_reasoning_available':False})
    if len(results)!=6:raise ValueError('EXPECTED_SIX_ORIGINAL_RECORDED_RUNS')
    return {'status':'PASS','runs':results,'total_events':sum(r['events'] for r in results),
            'original_feedback_enabled':any(r['trustkernel_feedback'] for r in results),
            'scope':'Raw hashchain and complete logical index parity; not semantic quality or source-world authenticity.'}


if __name__=='__main__':
    print(json.dumps(audit_sources(),indent=2))
