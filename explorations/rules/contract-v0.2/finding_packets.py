"""Lane-local findings on pinned recorded data. No verification imports or writes.

Use explicit CLI suite and assessment time to reproduce immutable packets.
All mappings/policies remain provisional; no accepted semantic support is emitted.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'verification/data/refined-v3').is_dir())
LANE = ROOT/'explorations/rules/contract-v0.2'
MAPPINGS_PATH = Path(__file__).with_name('mapping-snapshot.json')
MAPPINGS_PATH = MAPPINGS_PATH if MAPPINGS_PATH.exists() else LANE/'mappings.json'
PIN_PATH = Path(__file__).with_name('pin-snapshot.json')
PIN_PATH = PIN_PATH if PIN_PATH.exists() else LANE/'pin.json'
CASES_PATH = Path(__file__).with_name('case-snapshot.json')
CASES_PATH = CASES_PATH if CASES_PATH.exists() else LANE/'case-registry.json'
VERSION = '0.2.0'
BUILD = 'refined-v3-99d181ef7ca54fea4ff1'
CANONICAL = '950d60f56d835d08cb01fa4bd24d93153ce48ab211bcc1b2f630b35a815a3556'
STATUSES = {'PASS', 'FAIL', 'INCONCLUSIVE', 'NOT_APPLICABLE', 'ERROR'}
VERSIONS = ('schema_version', 'normalization_version', 'extraction_version')
LIMITS = [
    'Mechanical result conditional on declared mapping, corpus and prerequisites; not semantic ground truth.',
    'Recorded content transfer is not attention, reliance or accepted factual support.',
    'Hash identity does not authenticate a publisher or establish real-world truth.',
    'No complete extraction, semantic search, general quality score or dependency propagation.',
]


class BindingError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(value, pointer):
    if pointer == '':
        return value
    if not pointer.startswith('/'):
        raise BindingError('INVALID_JSON_POINTER')
    for token in pointer[1:].split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def decimal_value(text):
    if not isinstance(text, str) or not re.fullmatch(r'[+-]?(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?', text):
        raise BindingError('INVALID_DECIMAL_SYNTAX')
    try:
        value = Decimal(text.replace(',', ''))
    except InvalidOperation as exc:
        raise BindingError('INVALID_DECIMAL_SYNTAX') from exc
    if not value.is_finite():
        raise BindingError('NONFINITE_DECIMAL')
    return value


def compare_scalar(expected, observed, prerequisites):
    missing = [p['id'] for p in prerequisites if p['state'] != 'met']
    if missing:
        return 'INCONCLUSIVE', 'MISSING_OR_UNRESOLVED_PREREQUISITES', {'missing': missing}
    try:
        a, b = decimal_value(expected), decimal_value(observed)
    except BindingError as exc:
        return 'ERROR', str(exc), {'expected': expected, 'observed': observed}
    equal = a == b
    return ('PASS' if equal else 'FAIL'), ('SCALAR_EQUAL_UNDER_MAPPING' if equal else 'SCALAR_MISMATCH_UNDER_MAPPING'), {
        'expected_decimal': str(a), 'observed_decimal': str(b), 'equal': equal}


def prereq(id_, met, detail):
    return {'id': id_, 'state': 'met' if met else 'unresolved', 'detail': detail}


class Ledger:
    """Independent JSONL reader with read-only SQLite cross-checks and source gates."""
    def __init__(self, root=ROOT, pin_path=PIN_PATH):
        self.root = Path(root).resolve()
        self.pin = json.loads(Path(pin_path).read_text(encoding='utf-8'))
        self.files = {}
        self.source_cache = {}
        self.checked_rows = set()
        self.verified_sources = {}
        self.conn = None
        if self.pin['build_id'] != BUILD or self.pin['canonical_sha256'] != CANONICAL:
            raise BindingError('UNAPPROVED_RELEASE_PIN')
        for item in self.pin['artifacts']:
            path = self.path(item['path'])
            if sha(path) != item['sha256']:
                raise BindingError('PINNED_ARTIFACT_HASH_MISMATCH:' + item['path'])
            self.files[item['path']] = item['sha256']
        directory = self.root/'verification/data/refined-v3'
        self.manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        if self.manifest['build_id'] != BUILD or self.manifest['canonical_sha256'] != CANONICAL or sha(directory/'ledger.jsonl') != CANONICAL:
            raise BindingError('RELEASE_BINDING_MISMATCH')
        if self.manifest['versions'] != self.pin['release_versions']:
            raise BindingError('RELEASE_VERSION_MISMATCH')
        if self.manifest['accepted_support_claims'] != 0:
            raise BindingError('UNEXPECTED_ACCEPTED_SUPPORT')
        registry = json.loads((self.root/'verification/refinement_rules.json').read_text(encoding='utf-8'))
        overlay = json.loads((self.root/'verification/refinement_annotations.json').read_text(encoding='utf-8'))
        self.registry = registry
        if registry['registry_version'] != self.pin['registry_version']:
            raise BindingError('REGISTRY_VERSION_MISMATCH')
        if overlay['annotation_version'] != self.pin['authored_overlay_version']:
            raise BindingError('OVERLAY_VERSION_MISMATCH')
        rows = [json.loads(line) for line in (directory/'ledger.jsonl').read_text(encoding='utf-8').splitlines()]
        if len(rows) != self.pin['rows']:
            raise BindingError('ROW_COUNT_MISMATCH')
        self.rows = {row['id']: row for row in rows}
        if len(self.rows) != len(rows):
            raise BindingError('DUPLICATE_CANONICAL_ID')
        self.tables = defaultdict(list)
        for row in rows:
            self.tables[row['table']].append(row)
        for relative, expected in self.manifest.get('historical_hashes',{}).items():
            path='verification/'+relative
            if sha(self.path(path))!=expected:
                raise BindingError('HISTORICAL_RELEASE_HASH_MISMATCH:'+path)
            self.files[path]=expected
        for artifact in self.tables['artifacts']:
            if sha(self.path(artifact['path']))!=artifact['sha256']:
                raise BindingError('RECORDED_CORPUS_HASH_MISMATCH:'+artifact['path'])
            self.files[artifact['path']]=artifact['sha256']
        self.conn = sqlite3.connect((directory/'ledger.sqlite').as_uri()+'?mode=ro', uri=True)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA query_only=ON')
        metadata = dict(self.conn.execute('SELECT key,value FROM ledger_metadata'))
        if metadata.get('refined_sha256') != CANONICAL:
            self.close()
            raise BindingError('SQLITE_RELEASE_METADATA_MISMATCH')
        for table, table_rows in self.tables.items():
            if not re.fullmatch(r'[a-z][a-z0-9_]*', table):
                raise BindingError('INVALID_TABLE_NAME')
            count = self.conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if count != len(table_rows):
                raise BindingError('SQLITE_TABLE_COUNT_MISMATCH:' + table)

    def path(self, relative):
        path = (self.root/relative).resolve()
        if not path.is_relative_to(self.root):
            raise BindingError('SOURCE_PATH_OUTSIDE_ROOT')
        return path

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def row(self, id_, table=None):
        if id_ not in self.rows:
            raise BindingError('UNKNOWN_OR_STALE_ROW_ID:' + id_)
        row = self.rows[id_]
        if table and row['table'] != table:
            raise BindingError('ROW_TABLE_MISMATCH')
        if id_ not in self.checked_rows:
            saved = self.conn.execute(f'SELECT * FROM "{row["table"]}" WHERE id=?', (id_,)).fetchone()
            if saved is None:
                raise BindingError('SQLITE_MISSING_ROW')
            for key, observed in dict(saved).items():
                expected = row[key]
                if observed == expected:
                    continue
                try:
                    same = isinstance(observed, str) and json.loads(observed) == expected
                except (ValueError, TypeError):
                    same = False
                if not same:
                    raise BindingError('SQLITE_ROW_MISMATCH:' + id_ + ':' + key)
            self.checked_rows.add(id_)
        return row

    def select(self, table, **criteria):
        found = [r for r in self.tables[table] if all(r.get(k) == v for k,v in criteria.items())]
        if len(found) != 1:
            raise BindingError('SELECTOR_NOT_UNIQUE:' + table + ':' + canonical(criteria))
        return self.row(found[0]['id'], table)

    def row_ref(self, row):
        self.row(row['id'])
        return {'table': row['table'], 'id': row['id'], 'row_sha256': digest(row),
                'versions': {key: row[key] for key in VERSIONS}}

    def artifact(self, id_):
        row = self.row(id_, 'artifacts')
        path = self.path(row['path'])
        if row['path'] not in self.verified_sources:
            if sha(path) != row['sha256']:
                raise BindingError('SOURCE_ARTIFACT_HASH_MISMATCH:' + row['path'])
            self.verified_sources[row['path']] = row['sha256']
        if id_ not in self.source_cache:
            if path.suffix == '.jsonl':
                self.source_cache[id_] = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
            else:
                self.source_cache[id_] = json.loads(path.read_text(encoding='utf-8'))
        return row, self.source_cache[id_]

    def event(self, id_):
        row = self.row(id_, 'events')
        artifact, records = self.artifact(row['artifact_id'])
        found = [e for e in records if e.get('event_id') == row['event_id']]
        if len(found) != 1 or found[0] != row['raw'] or found[0]['event_hash'] != row['event_hash']:
            raise BindingError('EVENT_SOURCE_MISMATCH')
        return row, found[0], artifact

    def text(self, id_):
        row = self.row(id_, 'texts')
        artifact, container = self.artifact(row['artifact_id'])
        if row['event_id']:
            event, container, event_artifact = self.event(row['event_id'])
            if event_artifact['id'] != artifact['id']:
                raise BindingError('TEXT_EVENT_ARTIFACT_MISMATCH')
        value = resolve(container, row['pointer'])
        transform = row['transform']
        if transform:
            if transform == 'tool_return_prefix_then_json_parse:/evidence/content':
                match = re.match(r'^\[[a-z_]+ returned\]\n', value)
                if not match:
                    raise BindingError('TOOL_PREFIX_TRANSFORM_MISMATCH')
                value = value[match.end():]
            elif transform != 'json_parse:/evidence/content':
                raise BindingError('UNKNOWN_TEXT_TRANSFORM')
            value = resolve(json.loads(value), '/evidence/content')
        if value != row['text'] or hashlib.sha256(value.encode('utf-8')).hexdigest() != row['sha256']:
            raise BindingError('TEXT_SOURCE_MISMATCH')
        return row, artifact, value

    def anchor(self, text_id, start, end, quote):
        text, artifact, value = self.text(text_id)
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(value) or value[start:end] != quote:
            raise BindingError('SOURCE_SPAN_MISMATCH')
        left = value.rfind('\n\n', 0, start)
        left = 0 if left < 0 else left+2
        right = value.find('\n\n', end)
        right = len(value) if right < 0 else right
        return {'text_ref': self.row_ref(text), 'artifact_id': artifact['id'],
                'path': artifact['path'], 'artifact_sha256': artifact['sha256'],
                'pointer': text['pointer'], 'event_id': text['event_id'], 'transform': text['transform'],
                'start': start, 'end': end, 'quote': quote, 'offset_unit': 'decoded_unicode_code_points_half_open',
                'enclosing_context': {'start': left, 'end': right, 'quote': value[left:right]},
                'report_header_context': value[:value.find('\n\n')] if '\n\n' in value else value}

    def subject(self, occurrence):
        if occurrence['table'] == 'assertions':
            report = self.row(occurrence['report_id'], 'reports')
            source = self.select('sources_v2', report_id=report['id'])
            text_id = report['text_id']
        elif occurrence['table'] == 'clauses_v3':
            source = self.row(occurrence['source_id'], 'sources_v2')
            report = self.row(source['report_id'], 'reports') if source['report_id'] else None
            if not report:
                # Discussion sources are not needed for this bounded case set.
                raise BindingError('UNSUPPORTED_DISCUSSION_ANCHOR')
            text_id = report['text_id']
        else:
            raise BindingError('UNSUPPORTED_SUBJECT_GRAIN')
        prop = self.row(occurrence['proposition_id'])
        if occurrence['table']=='assertions' and (occurrence['run_id']!=source['run_id'] or
                occurrence['call_id']!=source['call_id'] or report['call_id']!=source['call_id'] or
                occurrence['output_event_id']!=source['output_event_id']):
            raise BindingError('OCCURRENCE_ORIGIN_SCOPE_MISMATCH')
        anchor = self.anchor(text_id, occurrence['start'], occurrence['end'], occurrence['quote'])
        if self.text(text_id)[2] != source['text']:
            raise BindingError('SOURCE_REPORT_TEXT_MISMATCH')
        call = self.row(source['call_id'], 'calls')
        if call['run_id'] != source['run_id']:
            raise BindingError('CROSS_RUN_SUBJECT_CALL')
        start, _, _ = self.event(call['start_event_id'])
        end, _, _ = self.event(source['output_event_id'])
        if start['run_id'] != end['run_id'] or start['run_id']!=source['run_id'] or start['seq'] >= end['seq'] or start['span_id']!=call['span_id'] or end['span_id']!=call['span_id']:
            raise BindingError('INVALID_SUBJECT_EVENT_ORDER')
        return {'occurrence': self.row_ref(occurrence), 'proposition_revision': self.row_ref(prop),
                'source': self.row_ref(source), 'run_id': source['run_id'], 'actor': source['actor'],
                'call_id': call['id'], 'input_event_id': start['id'], 'input_seq': start['seq'],
                'output_event_id': end['id'], 'output_seq': end['seq'], 'asserted_at': source['asserted_at'],
                'anchor': anchor, 'original_unresolved': prop.get('normalization', {}).get('unresolved', []),
                'original_identity_status': prop['identity_status']}

    def evidence(self, key):
        evidence = self.select('evidence', evidence_key=key)
        artifact, fixture = self.artifact(evidence['artifact_id'])
        item = resolve(fixture, evidence['pointer'])
        if item['content'] != evidence['content'] or item['evidence_id'] != key:
            raise BindingError('EVIDENCE_SOURCE_MISMATCH')
        return evidence, {'evidence_ref': self.row_ref(evidence), 'path': artifact['path'],
            'artifact_sha256': artifact['sha256'], 'pointer': evidence['pointer']+'/content',
            'start': 0, 'end': len(item['content']), 'quote': item['content'],
            'offset_unit': 'decoded_unicode_code_points_half_open', 'observed_at': item['observed_at'],
            'source_id': item.get('source_id'), 'root_source_id': item.get('root_source_id'),
            'scope': evidence['scope'], 'content_status': evidence['content_status']}, fixture

    def authored_span_subject(self, source, quote, author_mapping_id):
        """Exact unatomized recorded wording; explicit local identity, no invented ledger row."""
        report = self.row(source['report_id'], 'reports')
        if source['text'].count(quote) != 1:
            raise BindingError('AUTHORED_SPAN_NOT_UNIQUE')
        start = source['text'].index(quote)
        anchor = self.anchor(report['text_id'], start, start+len(quote), quote)
        authored = {'source_ref':self.row_ref(source), 'start':start, 'end':start+len(quote), 'quote':quote,
            'author':'Codex verification semantics lane', 'version':VERSION,
            'status':'authored_source_occurrence_not_a_canonical_ledger_assertion', 'mapping_id':author_mapping_id}
        prop = {'id':'authored-proposition:'+digest(authored), 'version':VERSION,
                'status':'provisional_wording_only_no_accepted_semantic_normalization'}
        call = self.row(source['call_id'], 'calls')
        before, _, _ = self.event(call['start_event_id'])
        after, _, _ = self.event(source['output_event_id'])
        if before['run_id'] != source['run_id'] or after['run_id'] != source['run_id'] or before['seq'] >= after['seq']:
            raise BindingError('AUTHORED_SPAN_EVENT_SCOPE_MISMATCH')
        return {'occurrence': {'namespace':'lane_authored_source_spans', 'id':'authored-occurrence:'+digest(authored),
                              'definition':authored}, 'proposition_revision':prop,
            'source':self.row_ref(source), 'run_id':source['run_id'], 'actor':source['actor'],
            'call_id':call['id'], 'input_event_id':before['id'], 'input_seq':before['seq'],
            'output_event_id':after['id'], 'output_seq':after['seq'], 'asserted_at':source['asserted_at'],
            'anchor':anchor, 'original_unresolved':['not_selected_as_a_canonical_assertion; authored exact span only'],
            'original_identity_status':'provisional_lane_authored_occurrence'}

    def exposure_witnesses(self, call_id, evidence_id):
        call = self.row(call_id, 'calls')
        result = []
        for row in self.tables['exposures']:
            if row['call_id'] != call_id or row['evidence_id'] != evidence_id:
                continue
            self.row(row['id'])
            if row['quote']!=self.row(evidence_id,'evidence')['content']:
                raise BindingError('EXPOSURE_EVIDENCE_CONTENT_MISMATCH')
            text, _, _ = self.text(row['text_id'])
            if text['event_id'] != call['start_event_id']:
                raise BindingError('EXPOSURE_CALL_SCOPE_MISMATCH')
            result.append({'exposure_ref': self.row_ref(row), 'mode': row['mode'],
                'provenance': row.get('provenance'),
                'anchor': self.anchor(row['text_id'], row['start'], row['end'], row['quote']),
                'meaning': 'Recorded input presence in this attempt only; no private reliance or factual support.'})
        return result

    def assert_unchanged(self):
        for path, expected in {**self.files, **self.verified_sources}.items():
            if sha(self.path(path)) != expected:
                raise BindingError('INPUT_CHANGED_DURING_ASSESSMENT:' + path)


def envelope(ledger, case_id, type_, method, subject, mapping, context, prerequisites,
             expected, observed, status, reason, assessed_at, positive=None, negative=None,
             assumptions=None, limits=None, supersedes=None):
    if status not in STATUSES:
        raise BindingError('INVALID_RESULT_STATUS')
    if supersedes is not None and not re.fullmatch(r'finding:[0-9a-f]{64}',supersedes):
        raise BindingError('INVALID_SUPERSEDES_ID')
    if status in {'PASS', 'FAIL'} and any(p['state'] != 'met' for p in prerequisites):
        raise BindingError('DEFINITE_RESULT_WITH_UNMET_PREREQUISITES')
    stamp = datetime.fromisoformat(assessed_at.replace('Z','+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise BindingError('ASSESSMENT_TIMESTAMP_MUST_BE_UTC')
    result = {'finding_contract_version': VERSION, 'case_id': case_id,
        'check': {'check_id': 'check:'+digest({'case': case_id, 'method': method, 'mapping': mapping, 'context': context}),
                  'type': type_, 'method_version': method, 'implementation_sha256': sha(Path(__file__))},
        'subject': subject, 'ledger_context': {'build_id': BUILD, 'canonical_sha256': CANONICAL,
            'release_versions': ledger.pin['release_versions'], 'registry_version': ledger.pin['registry_version'],
            'authored_overlay_version': ledger.pin['authored_overlay_version'], 'context': context},
        'mapping': mapping, 'required_prerequisites': prerequisites,
        'expected': expected, 'observed': observed,
        'result': {'status': status, 'reason_code': reason},
        'positive_witnesses': positive or [], 'negative_witnesses': negative or [],
        'assumptions': assumptions or [], 'limits': LIMITS + (limits or []),
        'assessed_at': assessed_at, 'supersedes': supersedes,
        'accepted_factual_support': False}
    result['finding_id'] = 'finding:'+digest(result)
    if supersedes == result['finding_id']:
        raise BindingError('SELF_SUPERSESSION')
    return result


def scalar_case(ledger, mapping, assessed_at):
    occurrence = ledger.select('assertions', **mapping['selector'])
    subject = ledger.subject(occurrence)
    prop = ledger.row(occurrence['proposition_id'])
    report_text = ledger.text(ledger.row(occurrence['report_id'])['text_id'])[2]
    evidence, witness, fixture = ledger.evidence(mapping['evidence_key'])
    required = ['entity','predicate','value','unit','valid_date','evidence_column']
    prerequisites = [prereq('mapping_fields', all(mapping.get(k) for k in required), 'Authored fields must all be explicit; no inference from omitted unit/date.')]
    prerequisites.append(prereq('authored_mapping_status',mapping.get('status')=='provisional_complete_for_conditional_comparison' and bool(mapping.get('version')),
                                'Only an explicitly complete provisional mapping is executable; completeness is not semantic acceptance.'))
    anchor_ok = all(occurrence[k] == mapping['anchor'][k] for k in ('start','end','quote'))
    prerequisites += [prereq('authored_anchor_gate', anchor_ok and all(q in report_text for q in mapping['context_quotes']),
                              'Exact token and authored context quotes match; this gate is not semantic adjudication.'),
        prereq('entity_date_unit_alignment', prop['entity']==mapping['entity'] and prop['predicate']==mapping['predicate'] and
            prop['unit']==mapping['unit'] and prop['valid_time'].get('date')==mapping['valid_date'] and
            fixture['ticker']==mapping['entity'] and fixture['as_of']==mapping['valid_date'],
            'Candidate parent proposition and explicit fixture instrument/date agree with this mapping.'),
        prereq('corpus_scope', mapping['scope']=='fixture_consistency', 'This comparator checks the pinned fixture, not current real prices.'),
        prereq('price_unit_and_column', evidence['content'].splitlines()[0]==mapping['evidence_unit_context'] and
            mapping['unit']=='USD' and mapping['predicate']=='close' and mapping['evidence_column']=='Close',
            'This narrow implementation supports declared USD Close price only.')]
    run=ledger.select('runs',run_id=subject['run_id'])
    prerequisites.append(prereq('fixture_identity',evidence['fixture_hash']==run['fixture_hash'] and prop['scope']=='fixture:'+run['fixture_hash'],
                                'Run, evidence and candidate scope identify the same logical fixture; file-byte hash is a separate identity.'))
    data = list(csv.DictReader(io.StringIO(evidence['content'].split('\n',1)[1])))
    matches = [r for r in data if r.get('Date')==mapping['valid_date']]
    prerequisites.append(prereq('unique_dated_row', len(matches)==1, 'Exactly one CSV row matches the mapped date.'))
    observed = matches[0].get(mapping['evidence_column']) if len(matches)==1 else None
    expected = occurrence['quote']
    status, reason, comparison = compare_scalar(expected, observed, prerequisites)
    if status in {'PASS','FAIL'}:
        try:
            if decimal_value(expected)!=decimal_value(mapping['value']) or decimal_value(expected)!=decimal_value(prop['value']):
                status, reason = 'INCONCLUSIVE', 'AUTHORED_VALUE_MAPPING_DISAGREES'
        except BindingError as exc:
            status,reason='ERROR','AUTHORED_VALUE_PARSE_ERROR'
            comparison['error']=str(exc)
    exposures = ledger.exposure_witnesses(subject['call_id'], evidence['id'])
    mapping_info = {**mapping, 'author': 'Codex verification semantics lane',
                    'registry_version': VERSION, 'registry_sha256': sha(MAPPINGS_PATH)}
    return envelope(ledger, mapping['id'], 'scalar_fixture_consistency', 'decimal_close_mapping_v0.2.0',
        subject, mapping_info,
        {'corpus': 'pinned_synthetic_fixture', 'evidence_id': evidence['id'],
         'valid_date': mapping['valid_date'], 'support_search': 'not_performed',
         'search_completeness': 'not_a_support_search', 'independent_corroboration': 'not_established'},
        prerequisites, {'value': expected, 'unit': mapping['unit'], 'role': mapping['predicate']},
        {'value': observed, 'comparison': comparison, 'recorded_input_exposures': exposures},
        status, reason, assessed_at, positive=[witness] if status=='PASS' else [],
        negative=[witness] if status=='FAIL' else [], assumptions=mapping['assumptions'],
        limits=['Input exposure is reported separately and is not a prerequisite of repository fixture consistency.',
                'The incomplete companion deliberately omits a unit; it is not a new allegation about the agent.'])


def root_relation(a, b):
    if not isinstance(a,str) or not isinstance(b,str) or not a.strip() or not b.strip():
        return 'INCONCLUSIVE', 'ROOT_IDENTITY_UNKNOWN', None
    if a == b:
        return 'PASS', 'DECLARED_ROOT_SHARED', True
    return 'INCONCLUSIVE', 'DISTINCT_ROOTS_DO_NOT_ESTABLISH_INDEPENDENCE', False


def condition_bounds(text, clause, normalization):
    """Verify local source/semicolon bounds, not the semantic attachment itself."""
    scope=normalization['scope']
    lo,hi=scope['attachment_start'],scope['attachment_end']
    if not 0<=lo<=clause['start']<clause['end']<=hi<=len(text):
        raise BindingError('CLAUSE_OUTSIDE_LOCAL_BRANCH')
    if ';' in text[lo:hi]:
        raise BindingError('ATTACHMENT_BRANCH_CONTAINS_SEMICOLON')
    for condition in normalization.get('condition_spans',[]):
        marker=condition['marker']
        if not (lo<=marker['start']<marker['end']<=condition['start']<condition['end']<=hi):
            raise BindingError('CONDITION_OUTSIDE_LOCAL_BRANCH')
        if text[condition['start']:condition['end']]!=condition['text'] or text[marker['start']:marker['end']]!=marker['text']:
            raise BindingError('CONDITION_SOURCE_SPAN_MISMATCH')
    return True


def rationale_roles(text, positive, positive_norm, rejected, rejected_norm):
    if positive['frame_id']!=rejected['frame_id'] or positive['source_id']!=rejected['source_id']:
        raise BindingError('REASON_PAIR_NOT_SAME_FRAME')
    for clause,norm,role,word in [(positive,positive_norm,'declared_reason','because'),
                                 (rejected,rejected_norm,'rejected_reason','not because')]:
        marker=norm.get('connector')
        if clause['role']!=role or not marker or marker['text']!=word:
            raise BindingError('REASON_ROLE_MARKER_MISMATCH')
        if text[marker['start']:marker['end']]!=word or marker['end']>clause['start']:
            raise BindingError('REASON_MARKER_SPAN_MISMATCH')
        if text[marker['end']:clause['start']].strip() or marker['start']<norm['scope']['attachment_start']:
            raise BindingError('REASON_MARKER_NOT_LOCAL_AND_ADJACENT')
        if text[clause['start']:clause['end']]!=clause['quote']:
            raise BindingError('REASON_CLAUSE_SPAN_MISMATCH')
    return {'positive_role':positive['role'], 'positive_marker':positive_norm['connector'],
            'rejected_role':rejected['role'], 'rejected_marker':rejected_norm['connector'],
            'rejected_reason_promoted_to_support':False, 'logical_sufficiency_established':False}


def extra_cases(ledger, assessed_at, registry):
    cases=registry['cases']
    findings=[]

    def emit(name,type_,subject,spec,prerequisites,expected,observed,status,reason,
             corpus,positive=None,negative=None,limits=None,context=None):
        mapping={'id':name, 'author':registry['author'], 'version':registry['version'],
            'status':registry['status'], 'registry_sha256':sha(CASES_PATH), 'definition':spec,
            'gate_note':'Selection and check policy are authored; exact anchors and explicit prerequisites are mechanically tested.'}
        ctx={'corpus':corpus,'run_id':subject['run_id'],'call_id':subject['call_id'],
             'support_search':'not_performed','search_completeness':'no_semantic_completeness_claim',**(context or {})}
        finding=envelope(ledger,name,type_,type_+'_v0.2.0',subject,mapping,ctx,
            prerequisites,expected,observed,status,reason,assessed_at,positive,negative,
            assumptions=spec.get('assumptions',[]),limits=limits)
        findings.append(finding)
        return finding

    # Access is its own finding, not an ingredient silently upgrading equality to truth.
    close=ledger.select('assertions',run_id='terra-2f66dbe7f15d',rule_id='market.ohlcv.close')
    subject=ledger.subject(close)
    price,price_anchor,_=ledger.evidence('E_PRICE')
    exposures=ledger.exposure_witnesses(subject['call_id'],price['id'])
    emit('ACCESS-TERRA-CLOSE','recorded_call_access',subject,
         {'evidence_key':'E_PRICE','detector':'exact ledger exposure with source transform/call/event gates'},
         [prereq('exact_subject_call',True,'Call resolved from recorded report origin; attempt identity retained.')],
         {'full_content_presence':True}, {'full_content_presence':bool(exposures),'recorded_input_exposures':exposures},
         'PASS' if exposures else 'INCONCLUSIVE', 'EXACT_CONTENT_IN_THIS_INPUT' if exposures else 'NO_FULL_MATCH_BY_DECLARED_DETECTOR',
         'recorded_single_call_input',positive=[x['anchor'] for x in exposures],
         context={'input_event_id':subject['input_event_id'],'event_cutoff_seq':subject['input_seq']})

    # No canonical atom selected this exact omission wording: preserve that limitation explicitly.
    spec=cases['snapshot_protocol']
    source=ledger.select('sources_v2',run_id=spec['run_id'],source_type=spec['source_type'])
    subject=ledger.authored_span_subject(source,spec['quote'],'PROTOCOL-SOL-SNAPSHOT')
    candidates=[]
    for t in ledger.tables['texts']:
        if t['event_id'] is None or t['transform'] is not None or spec['instruction'] not in t['text']:
            continue
        event=ledger.row(t['event_id'],'events')
        if event['run_id']==source['run_id'] and event['kind']=='llm.start' and event['seq']<source['output_seq']:
            candidates.append((event,t))
    if not candidates:
        raise BindingError('ANCHORED_PROTOCOL_INSTRUCTION_ABSENT')
    first,text=min(candidates,key=lambda pair:pair[0]['seq'])
    instruction_at=text['text'].index(spec['instruction'])
    instruction=ledger.anchor(text['id'],instruction_at,instruction_at+len(spec['instruction']),spec['instruction'])
    all_events=sorted((e for e in ledger.tables['events'] if e['run_id']==source['run_id']),key=lambda e:e['seq'])
    # Resolve the whole bounded raw prefix, including absence-query candidates, not just positive hits.
    prefix=[e for e in all_events if e['seq']<source['output_seq']]
    for event in prefix:ledger.event(event['id'])
    contiguous=[e['seq'] for e in prefix]==list(range(1,source['output_seq']))
    end_events=[e for e in all_events if e['kind']=='run.end']
    completed=bool(end_events) and ledger.event(end_events[-1]['id'])[1]['payload'].get('status')=='success'
    invocations=[e for e in prefix if e['kind']=='tool.start' and e['raw']['payload'].get('tool',{}).get('name')==spec['tool_name']]
    retrieved=[e for e in prefix if e['kind']=='evidence.retrieved' and e['raw']['payload'].get('evidence',{}).get('evidence_id')==spec['evidence_key']]
    prereqs=[prereq('recorded_instruction',True,'Exact before-final-report obligation present in earliest matching input.'),
             prereq('complete_recorded_prefix',contiguous and completed,'Dense saved event sequence and successful run termination; capture completeness outside recording not asserted.')]
    status='INCONCLUSIVE' if any(p['state']!='met' for p in prereqs) else ('PASS' if invocations else 'FAIL')
    artifact,_=ledger.artifact(prefix[0]['artifact_id'])
    prefix_witness={'path':artifact['path'],'artifact_sha256':artifact['sha256'],'pointer':None,
        'selector':{'seq_start':1,'seq_end_exclusive':source['output_seq'],'run_id':source['run_id'],
                    'query':'kind=tool.start AND payload.tool.name=get_verified_market_snapshot'},
        'event_row_refs':[ledger.row_ref(e) for e in prefix],
        'meaning':'Completed bounded saved-prefix absence query; not global support absence.'}
    emit('PROTOCOL-SOL-SNAPSHOT','required_tool_protocol',subject,spec,prereqs,
         {'required_invocation_before_report':True},
         {'invocations':len(invocations),'retrievals':len(retrieved),'prefix_contiguous':contiguous,'run_completed':completed},
         status,'REQUIRED_INVOCATION_MISSING_IN_RECORDED_PREFIX' if status=='FAIL' else 'PROTOCOL_QUERY_RESULT',
         'recorded_event_prefix',positive=[instruction],negative=[prefix_witness] if status=='FAIL' else [],
         limits=['Protocol failure does not establish unsupported numerical reasoning or conclusion falsity.',
                 'No source statement asserting an exact Sol close value is invented.'],
         context={'event_cutoff_seq':source['output_seq'],'protocol_search_completeness':'complete_saved_prefix_only'})

    spec=cases['sol_price_relation']
    occurrence=ledger.select('assertions',**spec['selector']);subject=ledger.subject(occurrence)
    ev,anchor,fixture=ledger.evidence(spec['evidence_key'])
    data=list(csv.DictReader(io.StringIO(ev['content'].split('\n',1)[1])))
    dated={row['Date']:row for row in data}
    row,previous=dated.get(spec['valid_date']),dated.get(spec['previous_date'])
    prereqs=[prereq('authored_exact_quote',occurrence['quote']==spec['quote'],'Exact selected quote; both conjuncts remain visible.'),
             prereq('dated_rows_and_price_unit',bool(row and previous) and fixture['ticker']==spec['entity'] and
                     fixture['as_of']==spec['valid_date'] and spec['unit']=='USD' and ev['content'].startswith('Synthetic OHLCV CSV, USD\n'),
                     'Explicit dated rows and fixture price-unit mapping; semantic session mapping remains authored.')]
    comparison=None
    if all(p['state']=='met' for p in prereqs):
        comparison=decimal_value(row['Close'])<decimal_value(row['Open']) and decimal_value(row['Close'])<decimal_value(previous['Close'])
    emit('PRICE-SOL-RELATION','derived_fixture_relation',subject,spec,prereqs,
         {'both_comparisons':True}, {'close':row['Close'] if row else None,'open':row['Open'] if row else None,
           'previous_close':previous['Close'] if previous else None,'both_comparisons':comparison,
           'recorded_input_exposures':ledger.exposure_witnesses(subject['call_id'],ev['id'])},
         'INCONCLUSIVE' if comparison is None else ('PASS' if comparison else 'FAIL'),
         'RELATION_CHECKED_UNDER_AUTHORED_SESSION_MAPPING','pinned_synthetic_fixture',
         positive=[anchor] if comparison else [], negative=[anchor] if comparison is False else [],
         limits=['CSV consistency is separate from missing required snapshot; CSV/snapshot are not independently authored sources.'])

    spec=cases['news_roots']
    occurrence=ledger.select('assertions',**spec['selector']);subject=ledger.subject(occurrence)
    left,left_anchor,_=ledger.evidence(spec['evidence_keys'][0]);right,right_anchor,_=ledger.evidence(spec['evidence_keys'][1])
    status,reason,shared=root_relation(left['root_source_id'],right['root_source_id'])
    emit('NEWS-DECLARED-ROOT','declared_lineage_relation',subject,spec,
         [prereq('exact_duplicate_quote',occurrence['quote']==spec['quote'],'Exact source wording selected.')],
         {'shared_known_declared_root':True},{'left_root':left['root_source_id'],'right_root':right['root_source_id'],'shared_known_root':shared},
         status,reason,'pinned_fixture_declared_lineage',positive=[left_anchor,right_anchor] if shared else [],
         limits=['Declared common root disqualifies distinct-original-reporting corroboration; no forensic provenance or statistical independence estimate.'])

    spec=cases['prediction_missing']
    occurrence=ledger.select('assertions',**spec['selector']);subject=ledger.subject(occurrence)
    ev,anchor,_=ledger.evidence(spec['evidence_key'])
    exposures=ledger.exposure_witnesses(subject['call_id'],ev['id'])
    prereqs=[prereq('exact_missingness_quote',occurrence['quote']==spec['quote'],'No numeric probability is asserted in this selected occurrence.'),
             prereq('exact_no_data_result',ev['content_status']=='NO_DATA' and ev['content']==spec['expected_content'],'Explicit tool fixture missingness, not world-event absence.'),
             prereq('this_call_delivery',bool(exposures),'At least one exact result-content occurrence in this attempt.')]
    status='PASS' if all(p['state']=='met' for p in prereqs) else 'INCONCLUSIVE'
    emit('PREDICTION-MISSINGNESS','tool_returned_missingness',subject,spec,prereqs,
         {'content_status':'NO_DATA'},{'content_status':ev['content_status'],'numeric_probability':None,'recorded_input_exposures':exposures},
         status,'EXPLICIT_MISSINGNESS_OBSERVED','recorded_single_call_input',positive=[anchor],
         limits=['Observed missing evidence does not establish zero event probability or absence of real-world markets.'])
    emit('PREDICTION-SCALAR-APPLICABILITY','probability_comparison_domain',subject,spec,
         [prereq('identified_subject_kind',True,'This source occurrence is missingness, not an asserted probability.')],
         {'required_domain':'numeric_probability_observation'},{'actual_domain':'missing_data_observation','probability':None,'coerced_zero':False},
         'NOT_APPLICABLE','MISSINGNESS_IS_NOT_A_NUMERIC_PROBABILITY','recorded_single_call_input',positive=[anchor],
         limits=['This asks applicability, not whether an actual zero-probability claim was false. No zero claim was found or fabricated.'])

    spec=cases['conditional_hold']
    clause=ledger.row(spec['clause_id'],'clauses_v3');subject=ledger.subject(clause)
    norm=ledger.row(clause['proposition_id'])['normalization']
    source=ledger.row(clause['source_id'])
    condition_bounds(source['text'],clause,norm)
    prereqs=[prereq('conditional_source_gate',clause['quote']==spec['quote'] and bool(norm['condition_spans']),
                    'Exact conditional wording and local marker spans are retained, not asserted true.')]
    prereqs += [prereq(key,spec['available_policy_inputs'].get(key) is not None, 'Not supplied in this case registry; no inference of actual portfolio state.') for key in spec['required_inputs']]
    emit('HOLD-CONDITIONAL-APPLICABILITY','decision_policy_applicability',subject,spec,prereqs,
         {'policy_inputs_required':spec['required_inputs']},{'available_policy_inputs':spec['available_policy_inputs'],
              'retained_condition_spans':norm['condition_spans'],'nested_and_coordination_unresolved':norm['unresolved']},
         'INCONCLUSIVE','PORTFOLIO_AND_POLICY_PREREQUISITES_MISSING','recorded_conditional_recommendation',
         positive=[subject['anchor']],limits=['Hold report declaration is not an unconditional instruction or price forecast.',
             'The local only-if and inherited invested context do not establish their referents, truth or Boolean scope.'])

    spec=cases['semicolon_regression']
    early=ledger.row(spec['earlier_clause_id'],'clauses_v3');later=ledger.row(spec['later_clause_id'],'clauses_v3')
    subject=ledger.subject(early);other=ledger.subject(later)
    first=ledger.row(early['proposition_id'])['normalization'];second=ledger.row(later['proposition_id'])['normalization']
    source=ledger.row(early['source_id']); text=source['text']
    condition_bounds(text,early,first);condition_bounds(text,later,second)
    correct=early['frame_id']==later['frame_id'] and not first['condition_spans'] and second['condition_spans'][0]['text']==spec['expected_antecedent']
    emit('R035-REAL-SEMICOLON','condition_attachment_boundary',subject,spec,
         [prereq('same_frame_source',early['source_id']==later['source_id'] and early['frame_id']==later['frame_id'],'Exact corrected real-source children.')],
         {'earlier_typed_guards':0,'later_antecedent':spec['expected_antecedent'],'cross_branch_attachment':False},
         {'earlier_typed_guards':len(first['condition_spans']),'later_condition_spans':second['condition_spans'],
          'earlier_branch':first['scope'],'later_branch':second['scope'],'cross_branch_attachment':False},
         'PASS' if correct else 'FAIL','LOCAL_BRANCH_INVARIANT_CHECKED','recorded_source_local_branch',
         positive=[subject['anchor'],other['anchor']],limits=['No claim that earlier advice is unconditionally suitable; full coordination and scope issues remain unresolved.'])

    spec=cases['reason_roles']
    pos=ledger.row(spec['positive_clause_id'],'clauses_v3');neg=ledger.row(spec['rejected_clause_id'],'clauses_v3')
    subject=ledger.subject(pos);other=ledger.subject(neg)
    pnorm=ledger.row(pos['proposition_id'])['normalization'];nnorm=ledger.row(neg['proposition_id'])['normalization']
    text=ledger.row(pos['source_id'])['text']
    observed=rationale_roles(text,pos,pnorm,neg,nnorm)
    emit('RATIONALE-POSITIVE-REJECTED','author_reason_role_boundary',subject,spec,
         [prereq('source_marker_role_gates',True,'Same frame, exact marker and exact clause bounds checked.')],
         {'positive_role':'declared_reason','rejected_role':'rejected_reason'},observed,
         'PASS','DECLARED_AND_REJECTED_REASON_ROLES_RETAINED','recorded_author_rationale',
         positive=[subject['anchor'],other['anchor']],limits=['A rejected explanation is not an assertion of its logical negation or an accepted negative witness about the world.'])
    emit('RATIONALE-SUFFICIENCY','stated_reason_support_applicability',subject,spec,
         [prereq('accepted_inference_rule',bool(spec['sufficiency_rule']),'No accepted rule from stated thin evidence to optimal Hold.'),
          prereq('accepted_support_relation',False,'Release establishes zero accepted factual-support relations.')],
         {'sufficient_justification_required':True},{'declared_reason':pos['quote'],'sufficiency_established':False},
         'INCONCLUSIVE','STATED_REASON_IS_NOT_ACCEPTED_SUPPORT','recorded_author_rationale',positive=[subject['anchor']],
         limits=['No automatic logical support or dependency invalidation from a because marker.'])
    return findings


def write_once(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise BindingError('REFUSE_CHANGED_BYTE_OVERWRITE:' + str(path))
        return
    with path.open('xb') as handle:
        handle.write(data)


def readable(findings):
    lines = ['# Scoped claim to evidence findings', '',
        'Version 0.2.0. Mechanical findings on a pinned synthetic recorded corpus; authored mappings remain provisional. Accepted factual-support relations created: zero.', '',
        f'Ledger: `{BUILD}`; canonical SHA-256 `{CANONICAL}`.', '']
    for finding in findings:
        a = finding['subject']['anchor']
        local = (ROOT/a['path']).as_posix()
        lines += [f'## {finding["case_id"]}', '',
            f'**{finding["result"]["status"]}** — `{finding["result"]["reason_code"]}`.', '',
            f'Question type: `{finding["check"]["type"]}`; corpus: `{finding["ledger_context"]["context"]["corpus"]}`.', '',
            f'Source: [{a["path"]}]({local}), `{a["pointer"]}`, [{a["start"]},{a["end"]}) Unicode code points.', '',
            '> '+a['quote'].replace('\n','\n> '), '',
            'Enclosing context: '+a['enclosing_context']['quote'].replace('\n',' '), '',
            'Mapping status: `'+str(finding['mapping'].get('status'))+'`; author: '+str(finding['mapping'].get('author'))+'.', '',
            'Expected: `'+canonical(finding['expected'])+'`.', '',
            'Observed: `'+canonical({k:v for k,v in finding['observed'].items() if k!='recorded_input_exposures'})+'`.', '',
            'Prerequisites: '+ '; '.join(p['id']+'='+p['state'] for p in finding['required_prerequisites'])+'.', '',
            'Meaning and limits: '+' '.join(finding['limits']), '']
        for polarity in ('positive_witnesses','negative_witnesses'):
            for witness in finding[polarity]:
                if 'path' in witness:
                    path=(ROOT/witness['path']).as_posix()
                    location=('selector `'+canonical(witness['selector'])+'`') if 'selector' in witness else f'`{witness.get("pointer")}`, [{witness.get("start")},{witness.get("end")})'
                    lines += [f'{polarity}: [{witness["path"]}]({path}), {location}.', '']
        exposures=finding['observed'].get('recorded_input_exposures',[])
        lines += [f'Recorded full evidence occurrences in the claim’s own input attempt: {len(exposures)}. This is a separate access observation.', '']
        for witness in exposures:
            anchor=witness['anchor']
            lines += [f'- `{witness["exposure_ref"]["id"]}`; mode `{witness["mode"]}`; `{anchor["pointer"]}`; transform `{anchor["transform"]}`.', '']
        if finding['assumptions']:
            lines += ['Authored assumptions: '+' '.join(finding['assumptions']), '']
    return '\n'.join(lines)+'\n'


def produce(suite, assessed_at):
    ledger = Ledger()
    try:
        registry = json.loads(MAPPINGS_PATH.read_text(encoding='utf-8'))
        findings = [scalar_case(ledger, mapping, assessed_at) for mapping in registry['mappings']]
        if suite == 'cases':
            registry_cases=json.loads(CASES_PATH.read_text(encoding='utf-8'))
            findings += extra_cases(ledger,assessed_at,registry_cases)
        elif suite != 'slice':
            raise BindingError('SUITE_NOT_IMPLEMENTED')
        inputs = {**ledger.files, **ledger.verified_sources}
        assessment_id = 'assessment-'+digest({'suite': suite, 'findings': [f['finding_id'] for f in findings]})[:24]
        directory = LANE/'assessments'/assessment_id
        packet = {'assessment_id': assessment_id, 'suite': suite, 'assessed_at': assessed_at,
                  'findings': findings, 'support_relations_created': 0}
        data = (canonical(packet)+'\n').encode('utf-8')
        report = readable(findings).encode('utf-8')
        manifest = {'assessment_id': assessment_id, 'suite': suite, 'assessed_at': assessed_at,
            'finding_contract_version': VERSION, 'pin': ledger.pin,
            'checked_canonical_sqlite_row_ids': sorted(ledger.checked_rows),
            'source_hashes': inputs, 'mapping_sha256': sha(MAPPINGS_PATH),
            'case_registry_sha256':sha(CASES_PATH) if suite=='cases' else None,
            'implementation_sha256': sha(Path(__file__)),
            'packet_sha256': hashlib.sha256(data).hexdigest(), 'readable_sha256': hashlib.sha256(report).hexdigest(),
            'results': {s:sum(f['result']['status']==s for f in findings) for s in sorted(STATUSES)},
            'model_calls': 0, 'network_calls': 0, 'source_writes': 0}
        ledger.assert_unchanged()
        write_once(directory/'packets.json', data)
        write_once(directory/'README.md', report)
        write_once(directory/'manifest.json', (json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))
        write_once(directory/'implementation.py', Path(__file__).read_bytes())
        write_once(directory/'mapping-snapshot.json', MAPPINGS_PATH.read_bytes())
        write_once(directory/'pin-snapshot.json', PIN_PATH.read_bytes())
        if suite=='cases':
            write_once(directory/'case-snapshot.json',CASES_PATH.read_bytes())
        ledger.assert_unchanged()
        return {'assessment_id': assessment_id, 'directory': str(directory), 'results':manifest['results'],
                'checked_sqlite_rows':len(ledger.checked_rows), 'verified_sources':len(ledger.verified_sources)}
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['slice','cases'], default='slice')
    parser.add_argument('--assessed-at', required=True, help='Explicit UTC ISO timestamp; reuse to reproduce bytes.')
    args = parser.parse_args()
    print(json.dumps(produce(args.suite,args.assessed_at),indent=2))


if __name__=='__main__':
    main()
