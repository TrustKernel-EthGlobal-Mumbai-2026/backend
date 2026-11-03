"""Reproduce selected exact evidence references; standard library, no inference/network.

Run from the Desktop TrustKernel directory. Writes only this lane's notes/.
Selections are worker-authored examples, not exhaustive or independent labels.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
SESSION = ROOT / 'runs/20261030-010033-30min-597a75'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strings(value, pointer=''):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from strings(child, f'{pointer}/{i}')
    elif isinstance(value, dict):
        for key, child in value.items():
            key = key.replace('~', '~0').replace('/', '~1')
            yield from strings(child, f'{pointer}/{key}')


def ref(path, pointer, text, quote):
    start = text.index(quote)
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path),
                pointer=pointer, start=start, end=start + len(quote), quote=quote,
                offset_unit='decoded Unicode code points; start inclusive, end exclusive')


selections = [
    ('R01', 'terra-2f66dbe7f15d', 'market_report', 'close of **$2,540**', 'numeric equality'),
    ('R02', 'sol-0530a9827c2c', 'market_report', 'Daily highs and lows rise across the three supplied sessions.', 'order over a bounded sample'),
    ('R03', 'sol-0530a9827c2c', 'market_report', 'Daily high-to-low ranges widen across the supplied candles.', 'derived arithmetic versus ATR interpretation'),
    ('R04', 'sol-0530a9827c2c', 'market_report', 'The required `get_verified_market_snapshot` result was **not retrieved**, and no tool rounds remain.', 'required-tool compliance'),
    ('R05', 'terra-2f66dbe7f15d', 'market_report', 'The snapshot provides no earlier volume series against which to assess whether the latest volume was unusual.', 'snapshot-only versus call-visible evidence scope'),
    ('R06', 'sol-0530a9827c2c', 'news_report', 'Both items trace to the same root source, `S_SYNTHETIC_A`.', 'declared source lineage'),
    ('R07', 'terra-2f66dbe7f15d', 'news_report', 'The fixture contains an alleged increase in ETH demand, but identifies it as an **unverified synthetic desk note** with no flow data or independent corroboration.', 'allegation versus event modality'),
    ('R08', 'terra-2f66dbe7f15d', 'news_report', 'No ETH-USD price, trading volume, ETF flows, on-chain activity, or derivatives positioning was supplied.', 'actor-local evidence versus run-wide fixture'),
    ('R09', 'sol-0530a9827c2c', 'news_report', 'Missing data must not be interpreted as a zero probability.', 'NO_DATA versus numeric zero'),
    ('R10', 'terra-2f66dbe7f15d', 'final_trade_decision', 'if invested, maintain exposure only if it fits established concentration, liquidity and loss limits using verified prices.', 'conditional decision and unknown portfolio state'),
    ('R11', 'terra-2f66dbe7f15d', 'final_trade_decision', 'The synthetic $2,510 and $2,600 session extremes are investigation points, not validated stop levels;', 'observation versus decision threshold'),
    ('R12', 'sol-0530a9827c2c', 'final_trade_decision', '**Time Horizon**: not provided', 'missing horizon versus failed forecast'),
]


def main():
    result = dict(status='provisional worker-selected examples; no semantic gold labels',
                  session=SESSION.name, references=[], calls=[], evidence=[], artifacts=[])
    fixture_path = SESSION / 'fixture.json'
    fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
    for tool, item in fixture['tools'].items():
        r = ref(fixture_path, '/tools/' + tool + '/content', item['content'], item['content'])
        result['evidence'].append(dict(id=item['evidence_id'], tool=tool, reference=r,
                                       observed_at=item['observed_at'],
                                       root_source_id=item.get('root_source_id')))
    for rid in ('sol-0530a9827c2c', 'terra-2f66dbe7f15d'):
        final_path = SESSION / rid / 'final_state.json'
        trace_path = SESSION / rid / 'trace.jsonl'
        state = json.loads(final_path.read_text(encoding='utf-8'))
        events = [json.loads(x) for x in trace_path.read_text(encoding='utf-8').splitlines()]
        for id_, run, field, quote, issue in selections:
            if run != rid:
                continue
            item = dict(id=id_, run_id=rid, issue=issue,
                        reference=ref(final_path, '/' + field, state[field], quote))
            full = state[field]
            start = full.index(quote)
            left = full.rfind('\n\n', 0, start) + 2
            if left == 1:
                left = 0
            right = full.find('\n\n', start + len(quote))
            if right < 0:
                right = len(full)
            item['enclosing_paragraph_reference'] = dict(
                path=final_path.relative_to(ROOT).as_posix(), sha256=sha(final_path),
                pointer='/' + field, start=left, end=right, quote=full[left:right],
                offset_unit='decoded Unicode code points; start inclusive, end exclusive')
            item['scope_context_note'] = 'Interpret with full report and its headers; inheritance is a candidate semantic decision, not a string-equality proof.'
            # Direct full report equality, not paraphrase or structured-output rendering.
            origins = []
            for event in events:
                if event['kind'] != 'llm.end':
                    continue
                for pointer, text in strings(event['payload'], '/payload'):
                    if text == state[field]:
                        origins.append(dict(seq=event['seq'], event_hash=event['event_hash'],
                                            span_id=event['span_id'], pointer=pointer))
            item['exact_report_output_matches'] = origins
            result['references'].append(item)
        for event in events:
            if event['kind'] != 'llm.start':
                continue
            msgs = list(strings(event['payload'].get('messages', []), '/payload/messages'))
            full_exposure = {}
            decoded_exposure = {}
            for tool, ev in fixture['tools'].items():
                full_exposure[ev['evidence_id']] = [
                    dict(pointer=ptr, start=text.index(ev['content']),
                         end=text.index(ev['content']) + len(ev['content']))
                    for ptr, text in msgs if ev['content'] in text]
                decoded_exposure[ev['evidence_id']] = []
                for ptr, text in msgs:
                    prefix = f'[{tool} returned]\n'
                    if not text.startswith(prefix):
                        continue
                    try:
                        envelope = json.loads(text[len(prefix):])
                    except json.JSONDecodeError:
                        continue
                    saved = envelope.get('evidence', {})
                    if saved.get('evidence_id') == ev['evidence_id'] and saved.get('content') == ev['content']:
                        decoded_exposure[ev['evidence_id']].append(dict(
                            raw_message_pointer=ptr, encoded_envelope_start=len(prefix),
                            encoded_envelope_end=len(text), decoded_pointer='/evidence/content',
                            transform='recognized_tool_prefix_then_json_decode_v1',
                            decoded_text_sha256=hashlib.sha256(ev['content'].encode('utf-8')).hexdigest()))
            instructions = []
            for ptr, text in msgs:
                for line in text.splitlines():
                    if 'get_verified_market_snapshot' in line and any(
                        word in line.lower() for word in ('must', 'required', 'call')):
                        instructions.append(dict(pointer=ptr, quote=line))
            if event['seq'] < 145:
                result['calls'].append(dict(run_id=rid, seq=event['seq'],
                    event_hash=event['event_hash'], span_id=event['span_id'],
                    checkpoint_namespace=event['payload'].get('metadata', {}).get('metadata', {}).get('langgraph_checkpoint_ns'),
                    full_content_exposures=full_exposure,
                    decoded_envelope_exposures=decoded_exposure,
                    snapshot_instructions=instructions))
    source_paths = [fixture_path, SESSION/'experiment.json', SESSION/'analysis.json',
                    SESSION/'review_packets.json']
    for run in sorted(SESSION.iterdir()):
        if run.is_dir():
            for name in ('trace.jsonl', 'trace.sqlite', 'run_manifest.json', 'final_state.json'):
                path = run/name
                if path.exists():
                    source_paths.append(path)
    source_paths += sorted((ROOT/'references').glob('*.docx'))
    source_paths += [ROOT/'verification/CONTRACT.md', ROOT/'verification/schema.json',
                     ROOT/'verification/ledger.py', ROOT/'verification/data/pilot/manifest.json',
                     ROOT/'verification/data/pilot/coverage.json']
    for path in source_paths:
        result['artifacts'].append(dict(path=path.relative_to(ROOT).as_posix(),
                                        sha256=sha(path), bytes=path.stat().st_size))
    manifest=json.loads((ROOT/'verification/data/pilot/manifest.json').read_text(encoding='utf-8'))
    result['ledger_snapshot']=dict(build_id=manifest['build_id'], versions=manifest['versions'],
        canonical_sha256=manifest['canonical_sha256'],
        current_implementation_vs_manifest=[dict(path=path, declared_sha256=expected,
            observed_sha256=sha(ROOT/path), matches=sha(ROOT/path)==expected)
            for path,expected in manifest['implementation_hashes'].items()],
        note='Build provenance and current draft interface snapshot are distinct if any implementation hash differs; no rebuild was invoked.')
    dest = LANE/'notes/source-packet.json'
    dest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(references=len(result['references']), calls=len(result['calls']),
                         artifacts=len(result['artifacts']), output=str(dest))))


if __name__ == '__main__':
    main()
