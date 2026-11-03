"""Validate selected source anchors, not semantic interpretations."""
import copy
import hashlib
import json
from pathlib import Path

LANE = Path(__file__).resolve().parent
ROOT = LANE.parents[1]
data = json.loads((LANE / 'source_cases.json').read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compatibility(expected_hash, observed_hash):
    if observed_hash is None:
        return 'unavailable'
    return 'compatible_exact_bytes' if expected_hash == observed_hash else 'stale_referenced_build'


def resolve(value, pointer):
    for token in pointer.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def check_anchor(anchor):
    path = ROOT / anchor['artifact']
    assert sha(path) == anchor['artifact_sha256'], 'artifact hash mismatch'
    if path.suffix == '.jsonl':
        events = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
        source = next(e for e in events if e['seq'] == anchor['event_seq'])
        assert source['event_id'] == anchor['event_id']
        assert source['event_hash'] == anchor['event_hash']
    else:
        source = json.loads(path.read_text(encoding='utf-8'))
    text = resolve(source, anchor['json_pointer'])
    assert isinstance(text, str)
    assert text[anchor['start']:anchor['end']] == anchor['quote'], 'span mismatch'


anchors = []


def walk(value):
    if isinstance(value, dict):
        if {'artifact', 'artifact_sha256', 'json_pointer', 'start', 'end', 'quote'} <= value.keys():
            anchors.append(value)
        for child in value.values():
            walk(child)
    elif isinstance(value, list):
        for child in value:
            walk(child)


walk(data)
for anchor in anchors:
    check_anchor(anchor)
for relative, expected in data['source_hashes'].items():
    assert sha(ROOT / relative) == expected
ledger = data['draft_ledger_snapshot']
current_path = ROOT / ledger['path']
observed_hash = sha(current_path) if current_path.exists() else None
ledger_state = compatibility(ledger['sha256'], observed_hash)
manifest_path = current_path.parent / 'manifest.json'
current_manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
history = json.loads((LANE / 'ledger-reference-history.json').read_text(encoding='utf-8'))
historical_reference = history['initial_pilot_observation']
assert sha(LANE / 'source_cases.json') == history['retained_delivered_case_packet']['sha256'], 'captured packet changed'
assert ledger['sha256'] == history['retained_delivered_case_packet']['canonical_sha256']
before = (LANE / 'source_cases.json').read_bytes()

bad_span = copy.deepcopy(anchors[0])
bad_span['end'] -= 1
bad_hash = copy.deepcopy(anchors[0])
bad_hash['artifact_sha256'] = '0' * 64
rejected = []
for name, invalid in [('shortened_span', bad_span), ('mismatched_hash', bad_hash)]:
    try:
        check_anchor(invalid)
    except AssertionError:
        rejected.append(name)
assert len(rejected) == 2
stale_variant_state = compatibility(ledger['sha256'], '0' * 64)
assert stale_variant_state == 'stale_referenced_build'
unavailable_variant_state = compatibility(ledger['sha256'], None)
assert unavailable_variant_state == 'unavailable'
assert compatibility(ledger['sha256'], ledger['sha256']) == 'compatible_exact_bytes'
assert (LANE / 'source_cases.json').read_bytes() == before
result = {'scope': 'selected source anchors and bytes only; no semantic validation',
    'raw_source_validation': 'PASS',
    'validated_anchors': len(anchors), 'unchanged_source_files': len(data['source_hashes']),
    'ledger_compatibility': {
        'state': ledger_state,
        'captured_canonical_sha256': ledger['sha256'],
        'captured_build_id': None,
        'captured_build_id_note': 'Not retained in the captured case packet; canonical and manifest hashes are the retained build references.',
        'captured_versions': ledger['versions'],
        'captured_selected_assertion_records': len(ledger['selected_terra_market_assertions']),
        'observed_current_canonical_sha256': observed_hash,
        'observed_current_build_id': current_manifest.get('build_id'),
        'observed_current_manifest_canonical_sha256': current_manifest.get('canonical_sha256'),
        'observed_current_versions': current_manifest.get('versions'),
        'current_requery_compatible': ledger_state == 'compatible_exact_bytes',
        'case_ids_rebound': False,
        'interpretation': 'Raw anchors and captured records remain inspectable. A stale or unavailable derived build blocks current-ledger joins, not raw-source validation.'},
    'earlier_report_ledger_reference': {
        'state': compatibility(historical_reference['canonical_sha256'], observed_hash),
        'referenced_canonical_sha256': historical_reference['canonical_sha256'],
        'referenced_rows': historical_reference['rows'],
        'complete_earlier_case_packet_retained': False,
        'historical_rows_reconstructed_or_rebound': False,
        'note': 'Earlier textual observation is preserved separately; delivered case JSON already captured the later build. See ledger-reference-history.json.'},
    'invalid_in_memory_variants_rejected': rejected,
    'stale_ledger_variant': {'raw_source_validation': 'PASS',
        'ledger_compatibility': stale_variant_state, 'case_ids_rebound': False},
    'unavailable_ledger_variant': {'raw_source_validation': 'PASS',
        'ledger_compatibility': unavailable_variant_state, 'case_ids_rebound': False},
    'source_cases_sha256': sha(LANE / 'source_cases.json'),
    'versions': ledger['versions']}
(LANE / 'validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
