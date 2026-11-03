"""Disposable source navigator. Standard library; no runner imports or network.

Historical generator for the captured case packet. Existing output is protected.
Validate it with validate_cases.py. Regeneration against a later coherent ledger
requires a separate versioned packet; do not silently rebind captured case IDs.
"""
import csv
import hashlib
import io
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SESSION = ROOT / 'runs/20261030-010033-30min-597a75'
if (OUT / 'source_cases.json').exists():
    raise SystemExit('Captured source_cases.json is preserved. Run validate_cases.py; '
                     'a later-ledger walkthrough requires a coherent handoff and a new versioned packet.')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path, pointer, text, start=0, end=None):
    end = len(text) if end is None else end
    return {'artifact': path.relative_to(ROOT).as_posix(),
            'artifact_sha256': digest(path), 'json_pointer': pointer,
            'span_convention': 'decoded Unicode code points [start,end)',
            'start': start, 'end': end, 'quote': text[start:end]}


def excerpt(path, pointer, text, needle):
    start = text.index(needle)
    return ref(path, pointer, text, start, start + len(needle))


def strings(value, pointer=''):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, dict):
        for key, child in value.items():
            key = key.replace('~', '~0').replace('/', '~1')
            yield from strings(child, pointer + '/' + key)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from strings(child, pointer + '/' + str(i))


fixture_path = SESSION / 'fixture.json'
fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
run_data = {}
inventory = []
source_paths = [fixture_path, SESSION / 'experiment.json', SESSION / 'analysis.json',
                SESSION / 'review_packets.json']
for folder in sorted(SESSION.iterdir()):
    if not folder.is_dir() or not (folder / 'trace.jsonl').exists():
        continue
    trace = folder / 'trace.jsonl'
    events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    final = json.loads((folder / 'final_state.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder / 'run_manifest.json').read_text(encoding='utf-8'))
    counts = Counter(e['kind'] for e in events)
    run_data[folder.name] = (events, final)
    inventory.append({'run_id': folder.name, 'events': len(events),
                      'llm_start': counts['llm.start'], 'llm_end': counts['llm.end'],
                      'llm_error': counts['llm.error'],
                      'manifest_keys': sorted(manifest),
                      'snapshot_retrieval_seq': [e['seq'] for e in events
                          if e['kind'] == 'evidence.retrieved'
                          and 'E_SNAPSHOT' in json.dumps(e['payload'])]})
    source_paths.extend([trace, folder / 'final_state.json', folder / 'run_manifest.json'])

terra = 'terra-2f66dbe7f15d'
sol = 'sol-0530a9827c2c'
terra_events, terra_final = run_data[terra]
sol_events, sol_final = run_data[sol]
terra_state_path = SESSION / terra / 'final_state.json'
sol_state_path = SESSION / sol / 'final_state.json'
terra_trace = SESSION / terra / 'trace.jsonl'
price_quote = 'close of **$2,540**'
price = excerpt(terra_state_path, '/market_report', terra_final['market_report'], price_quote)
price['input_event_seq'] = 73
price['output_event_seq'] = 75
input_event = next(e for e in terra_events if e['seq'] == 73)
output_event = next(e for e in terra_events if e['seq'] == 75)
output_pointer = '/payload/response/generations/0/0/text'
assert output_event['payload']['response']['generations'][0][0]['text'] == terra_final['market_report']
price['output_report_pointer'] = output_pointer
snapshot = fixture['tools']['get_verified_market_snapshot']['content']
price['recorded_snapshot_exposures'] = [
    dict(ref(terra_trace, p, s, s.index(snapshot), s.index(snapshot) + len(snapshot)),
         event_seq=73, event_id=input_event['event_id'], event_hash=input_event['event_hash'])
    for p, s in strings(input_event.get('payload', {}).get('messages'), '/payload/messages')
    if snapshot in s]
assert price['recorded_snapshot_exposures']
price['fixture_snapshot'] = ref(fixture_path,
    '/tools/get_verified_market_snapshot/content', snapshot)
csv_content = fixture['tools']['get_stock_data']['content']
csv_rows = list(csv.DictReader(io.StringIO(csv_content.split('\n', 1)[1])))
mapped_row = next(row for row in csv_rows if row['Date'] == '2026-10-28')
mapped_amount = Decimal(price_quote.split('$')[1].split('*')[0].replace(',', ''))
price['conditional_numeric_check'] = {
    'mapping_status': 'manually selected entity/date/close/USD/synthetic scope',
    'method': 'Decimal equality; manual proposition mapping is a precondition',
    'fixture_pointer': '/tools/get_stock_data/content',
    'row_date': mapped_row['Date'], 'column': 'Close',
    'fixture_value': mapped_row['Close'], 'report_value': str(mapped_amount),
    'result': 'MATCH' if Decimal(mapped_row['Close']) == mapped_amount else 'MISMATCH',
    'semantic_support': 'not adjudicated by this script'}
price['scope'] = 'Exact report/output linkage and literal input presence; not private reliance or real-world truth'

omission_quote = 'The required `get_verified_market_snapshot` result was **not retrieved**'
omission = excerpt(sol_state_path, '/market_report', sol_final['market_report'], omission_quote)
omission['recorded_snapshot_retrieval_count'] = next(x for x in inventory
    if x['run_id'] == sol)['snapshot_retrieval_seq']
omission['literal_price_csv_input_occurrences'] = [
    {'event_seq': e['seq'], 'json_pointer': p}
    for e in sol_events if e['kind'] == 'llm.start'
    for p, s in strings(e['payload'].get('messages'), '/payload/messages')
    if fixture['tools']['get_stock_data']['content'] in s]

news = []
for run_id in (sol, terra):
    text = run_data[run_id][1]['news_report']
    matches = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if any(w in line.lower() for w in ('independent', 'unverified', 'same underlying', 'digest')):
            matches.append(ref(SESSION / run_id / 'final_state.json', '/news_report',
                               text, offset, offset + len(line.rstrip('\r\n'))))
        offset += len(line)
    events = run_data[run_id][0]
    origins = [e for e in events if e['kind'] == 'llm.end' and
        any(g.get('text') == text for batch in e['payload']['response'].get('generations', [])
            for g in batch)]
    context = []
    for end in origins:
        start = next(e for e in events if e['kind'] == 'llm.start'
                     and e['span_id'] == end['span_id'])
        delivered = [item['evidence_id'] for item in fixture['tools'].values()
            if any(item['content'] in s for _, s in strings(start['payload'].get('messages')))]
        context.append({'input_seq': start['seq'], 'output_seq': end['seq'],
                        'exact_full_content_evidence_ids': delivered})
    news.append({'run_id': run_id, 'selected_passages': matches[:8],
                 'origin_context': context})

fallback = []
for run_id, (events, _) in run_data.items():
    for i, e in enumerate(events):
        if e['kind'] == 'llm.error':
            fallback.append({'run_id': run_id, 'error_seq': e['seq'],
                'error_event': e, 'next_model_events': [
                    {'seq': x['seq'], 'kind': x['kind'], 'span_id': x.get('span_id')}
                    for x in events[i+1:] if x['kind'] in ('llm.start', 'llm.end', 'llm.error')][:4]})

ledger = ROOT / 'verification/data/pilot/ledger.jsonl'
rows = [json.loads(s) for s in ledger.read_text(encoding='utf-8').splitlines()]
by_id = {r['id']: r for r in rows}
pilot_manifest_path = ROOT / 'verification/data/pilot/manifest.json'
pilot_manifest = json.loads(pilot_manifest_path.read_text(encoding='utf-8'))
final_report = next(r for r in rows if r['table'] == 'reports'
    and r['run_id'] == terra and r['field'] == 'final_trade_decision')
final_call = by_id[final_report['call_id']]
final_input = by_id[final_call['start_event_id']]['raw']
final_exposures = [r for r in rows if r['table'] == 'exposures'
                  and r['call_id'] == final_call['id']]
incomplete_exposure = {
    'run_id': terra, 'input_event_seq': final_input['seq'],
    'output_event_seq': by_id[final_call['end_event_id']]['seq'],
    'call_id': final_call['id'],
    'exact_full_raw_evidence_content_ids': [item['evidence_id']
        for item in fixture['tools'].values() if any(item['content'] in text
            for _, text in strings(final_input['payload'].get('messages')))],
    'recorded_prior_report_exposures': [{'report_field': by_id[e['report_id']]['field'],
        'exposure_id': e['id'], 'mode': e['mode']} for e in final_exposures if e['report_id']],
    'note': 'Prior reports are delivered; full raw fixture exposure is not identified. Partial or paraphrased transmission remains unmeasured.'}
selected = []
for row in rows:
    if row['table'] != 'assertions':
        continue
    report = by_id[row['report_id']]
    if row['run_id'] == terra and report['field'] == 'market_report':
        text = by_id[report['text_id']]['text']
        assert text[row['start']:row['end']] == row['quote']
        selected.append({'assertion': row, 'proposition': by_id[row['proposition_id']],
                         'report': report, 'checks': [r for r in rows
                             if r['table'] == 'checks' and r['subject_id'] == row['id']]})

result = {'status': 'bounded_source_navigation_demonstration_not_a_verifier',
    'session': SESSION.name, 'source_hashes': {p.relative_to(ROOT).as_posix(): digest(p)
        for p in source_paths}, 'inventory': inventory,
    'price_case': price, 'snapshot_omission_case': omission,
    'news_lineage_case': {'root_source_ids': {name: fixture['tools'][name]['root_source_id']
        for name in ('get_news', 'get_global_news')}, 'reports': news},
    'fallback_cases': fallback,
    'incomplete_exposure_case': incomplete_exposure,
    'draft_ledger_snapshot': {'path': ledger.relative_to(ROOT).as_posix(),
        'sha256': digest(ledger), 'rows': len(rows),
        'manifest_sha256': digest(pilot_manifest_path),
        'versions': pilot_manifest['versions'],
        'implementation_hashes': pilot_manifest['implementation_hashes'],
        'selected_terra_market_assertions': selected},
    'limits': ['Selection is manual or lexical and incomplete.',
        'No semantic verdicts or independent labels are generated.',
        'Input presence is observable context, not causal reliance.',
        'No source mutation or external requests.']}
target = OUT / 'source_cases.json'
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'output': str(target), 'events': sum(r['events'] for r in inventory),
    'price_span': [price['start'], price['end']], 'fallbacks': len(fallback),
    'draft_ledger_market_assertions': len(selected)}, indent=2))
