"""Read-only descriptive analysis of traces, never fed back to research agents."""
import argparse
import json
import re
import sqlite3
import time
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path
from .billing import message_usage
from .trace import utc


def seconds(start, end):
    return (datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()


def analyze_session(session):
    session = Path(session)
    rows, packets = [], []
    for directory in sorted(p for p in session.iterdir() if p.is_dir()):
        database = directory / 'trace.sqlite'
        if not database.exists():
            continue
        with closing(sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True)) as db:
            events = [dict(seq=r[0], kind=r[1], timestamp=r[2], span_id=r[3], payload=json.loads(r[4]))
                      for r in db.execute('SELECT seq,kind,timestamp,span_id,payload_json FROM events ORDER BY seq')]
        if not events:
            continue
        context = events[0]['payload'].get('context', {})
        counts = Counter(e['kind'] for e in events)
        calls = {e['span_id']:e for e in events if e['kind']=='llm.start'}
        usages = message_usage([e['payload'] for e in events])
        stages, usage_ids, latencies = [], set(), []
        inputs = outputs = 0
        for event in events:
            if event['kind'] != 'llm.end':
                continue
            start = calls.get(event['span_id'])
            stage = start['payload'].get('metadata', {}).get('metadata', {}).get('langgraph_node', 'unlabeled') if start else 'unmatched'
            stages.append(stage)
            if start:
                latencies.append(dict(stage=stage, seconds=seconds(start['timestamp'], event['timestamp'])))
            for batch in event['payload']['response'].get('generations', []):
                for generation in batch:
                    msg = generation.get('message', {})
                    identity = msg.get('response_metadata', {}).get('id') or msg.get('id')
                    usage = msg.get('usage_metadata') or usages.get(identity)
                    if usage and identity not in usage_ids:
                        usage_ids.add(identity)
                        inputs += usage['input_tokens']
                        outputs += usage['output_tokens']
        retrieved = [e['payload'] for e in events if e['kind']=='evidence.retrieved']
        evidence_ids = sorted({e['evidence']['evidence_id'] for e in retrieved})
        tools = Counter(e['payload'].get('tool', {}).get('name', 'unknown') for e in events if e['kind']=='tool.start')
        requests = Counter(json.dumps([e.get('evidence', {}).get('evidence_id'), e.get('request')], sort_keys=True) for e in retrieved)
        paper = next((e['payload'].get('decision','') for e in reversed(events) if e['kind']=='decision.paper'), '') or ''
        rating = re.search(r'\*\*Rating\*\*:\s*(Buy|Overweight|Hold|Underweight|Sell)', paper, re.I)
        rates = (2,10) if context.get('arm')=='sol' else (1,5)
        row = dict(run_id=directory.name, arm=context.get('arm'), pair_id=context.get('pair_id'),
                   fixture_hash=context.get('fixture_hash'), mode=context.get('mode'),
                   status='success' if counts['run.end'] else ('failed' if counts['run.error'] else 'running'),
                   observed_seconds=seconds(events[0]['timestamp'],events[-1]['timestamp']),
                   llm_started=counts['llm.start'], llm_completed=counts['llm.end'], usage_calls=len(usage_ids),
                   unmatched_llm_starts=max(0,counts['llm.start']-counts['llm.end']),
                   errors=counts['run.error']+counts['llm.error']+counts['tool.error'],
                   tool_calls=sum(tools.values()), tools=dict(tools), evidence_retrievals=len(retrieved),
                   distinct_evidence_ids=evidence_ids, repeated_identical_retrievals=sum(n-1 for n in requests.values()),
                   input_tokens=inputs, output_tokens=outputs,
                   standard_cost_estimate_usd=(inputs*rates[0]+outputs*rates[1])/1e6 if usage_ids else None,
                   stages=dict(Counter(stages)), call_latencies=latencies, paper_rating=rating[1] if rating else None,
                   raw_trace=str(directory/'trace.jsonl'))
        final_path = directory/'final_state.json'
        if row['status']=='success' and final_path.exists():
            try:
                final = json.loads(final_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                final = {}
            for field, text in final.items():
                if not isinstance(text,str) or not text or not (field.endswith('_report') or field in ('investment_plan','trader_investment_plan','final_trade_decision')):
                    continue
                packets.append(dict(run_id=directory.name, arm=context.get('arm'), pair_id=context.get('pair_id'),
                                    field=field, report=text, source_artifact=str(final_path),
                                    explicit_evidence_ids=[identity for identity in evidence_ids if identity in text],
                                    review_status='unannotated; no truth/quality verdict'))
        rows.append(row)
    by_pair = {}
    for row in rows:
        by_pair.setdefault(row['pair_id'],[]).append(row)
    pairs = [dict(pair_id=key, arms=[r['arm'] for r in group],
                  identical_available_fixture=len({r['fixture_hash'] for r in group})==1 and len(group)==2,
                  both_completed=len(group)==2 and all(r['status']=='success' for r in group),
                  consumed_evidence_equal=len(group)==2 and group[0]['distinct_evidence_ids']==group[1]['distinct_evidence_ids'])
             for key, group in by_pair.items()]
    result = dict(updated_at=utc(), unit='one model workflow within a paired checkpoint', runs=rows, pairs=pairs,
                  total_estimated_standard_cost_usd=sum(r['standard_cost_estimate_usd'] or 0 for r in rows),
                  limitations=['Synthetic frozen fixture; no live market or profitability conclusion',
                               'Small repeated sample; order/load/token volume can affect latency',
                               'More tokens, calls, citations or graph nodes do not imply better reasoning',
                               'Equal available evidence does not imply equal consumed evidence',
                               'Groundedness and contradiction judgments require independent annotation'],
                  review_questions=['Does each numerical price/indicator claim match a supplied snapshot?',
                                    'Does the report acknowledge unavailable indicators, macro and prediction feeds?',
                                    'Does it treat the duplicated demand note as one unverified source?',
                                    'Which explicit assumptions support the final paper decision?',
                                    'Are materially different decisions explained by evidence use or unsupported claims?'])
    def write_json(name, value):
        temporary = session/(name+'.tmp')
        temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
        temporary.replace(session/name)
    write_json('analysis.json', result)
    write_json('review_packets.json', packets)
    lines = ['# Live trace analysis', '', f'Updated {result["updated_at"]}. Read-only, no extra model calls.', '',
             '| Model/run | Status | LLM done/started | Tool calls | Unique evidence | Tokens in/out | Est. USD | Paper rating |',
             '|---|---|---:|---:|---:|---:|---:|---|']
    for row in rows:
        cost = f"{row['standard_cost_estimate_usd']:.4f}" if row['standard_cost_estimate_usd'] is not None else 'unknown'
        lines.append(f"| {row['run_id']} | {row['status']} | {row['llm_completed']}/{row['llm_started']} | {row['tool_calls']} | {len(row['distinct_evidence_ids'])} | {row['input_tokens']}/{row['output_tokens']} | {cost} | {row['paper_rating'] or 'pending'} |")
    lines += ['', '## What to examine', '', *['- '+q for q in result['review_questions']], '',
              '## Interpretation limits', '', *['- '+q for q in result['limitations']], '',
              'Full report text and source artifact references are in review_packets.json. These are review inputs, not automated factuality scores.']
    (session/'analysis.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        result = analyze_session(args.session)
        print(f'{utc()} analysis: {len(result["runs"])} runs; reports in {args.session}',flush=True)
        if not args.watch or json.loads((args.session/'experiment.json').read_text())['status'] != 'running':
            break
        time.sleep(15)
