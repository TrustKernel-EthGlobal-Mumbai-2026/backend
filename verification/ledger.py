"""Offline ledger builder. Standard library only; no environment/credential inspection."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / 'runs/20261030-010033-30min-597a75'
VERSION = '1.1.0'
VERSIONS = dict(schema_version=VERSION, normalization_version=VERSION, extraction_version='1.0.0')
FIELDS = ('market_report', 'news_report', 'investment_plan', 'trader_investment_plan', 'final_trade_decision')

# JSON columns hold canonical serialized arrays/objects. All other columns are typed.
TABLES = {
    'artifacts': 'path TEXT sha256 TEXT bytes INTEGER',
    'runs': 'artifact_id TEXT run_id TEXT pair_id TEXT arm TEXT model TEXT fixture_hash TEXT config_hash TEXT session_config_hash TEXT',
    'events': 'artifact_id TEXT run_id TEXT seq INTEGER event_id TEXT timestamp TEXT kind TEXT span_id TEXT parent_id TEXT event_hash TEXT raw JSON',
    'evidence': 'artifact_id TEXT pointer TEXT fixture_hash TEXT evidence_key TEXT tool TEXT item_hash TEXT content TEXT content_status TEXT observed_at TEXT source_id TEXT root_source_id TEXT provider TEXT scope TEXT',
    'availability': 'run_id TEXT evidence_id TEXT event_id TEXT',
    'retrievals': 'run_id TEXT evidence_id TEXT event_id TEXT request JSON',
    'calls': 'run_id TEXT span_id TEXT actor TEXT start_event_id TEXT end_event_id TEXT error_event_id TEXT status TEXT',
    'texts': 'artifact_id TEXT event_id TEXT pointer TEXT transform TEXT text TEXT sha256 TEXT role TEXT',
    'exposures': 'call_id TEXT text_id TEXT evidence_id TEXT report_id TEXT start INTEGER end INTEGER quote TEXT mode TEXT provenance JSON',
    'mentions': 'report_id TEXT evidence_id TEXT start INTEGER end INTEGER quote TEXT form TEXT',
    'reports': 'run_id TEXT field TEXT text_id TEXT call_id TEXT output_event_id TEXT origin_method TEXT origin_pointer TEXT origin_args JSON',
    'propositions': 'entity TEXT predicate TEXT value JSON unit TEXT valid_time JSON scope TEXT modality TEXT assumptions JSON identity_status TEXT',
    'assertions': 'run_id TEXT report_id TEXT proposition_id TEXT call_id TEXT actor TEXT output_event_id TEXT asserted_at TEXT start INTEGER end INTEGER quote TEXT rule_id TEXT annotation_status TEXT',
    'links': 'assertion_id TEXT evidence_id TEXT report_id TEXT relation TEXT status TEXT basis TEXT mention_id TEXT',
    'checks': 'subject_table TEXT subject_id TEXT category TEXT method TEXT result TEXT details JSON',
}
FK = {
    'artifact_id': 'artifacts', 'evidence_id': 'evidence', 'text_id': 'texts',
    'call_id': 'calls', 'report_id': 'reports', 'proposition_id': 'propositions',
    'assertion_id': 'assertions', 'mention_id': 'mentions',
    'event_id': 'events', 'start_event_id': 'events', 'end_event_id': 'events',
    'error_event_id': 'events', 'output_event_id': 'events',
}
NULLABLE = {
    'events': {'span_id','parent_id'},
    'evidence': {'observed_at','source_id','root_source_id'},
    'calls': {'end_event_id','error_event_id'},
    'texts': {'event_id','transform','role'},
    'exposures': {'evidence_id','report_id'},
    'reports': {'call_id','output_event_id','origin_pointer','origin_args'},
    'propositions': {'unit','value'},
    'assertions': {'call_id','actor','output_event_id','asserted_at'},
    'links': {'evidence_id','report_id','mention_id'},
}
ENUMS = {
    ('evidence','content_status'): {'CONTENT','PARTIAL','NO_DATA','ERROR'},
    ('calls','status'): {'completed','error'},
    ('exposures','mode'): {'decoded_tool_result_lineage','decoded_envelope_presence','exact_evidence_text_in_message','exact_prior_report'},
    ('links','status'): {'agent-asserted','extractor-proposed','verified'},
    ('assertions','annotation_status'): {'worker_candidate_awaiting_independent_adjudication'},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()


def object_hash(value):
    # Matches the raw trace producer, whose separators include spaces.
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False))


def ident(table, identity):
    return table + ':' + sha(canonical(identity))


def columns(table):
    parts = TABLES[table].split()
    return list(zip(parts[::2], parts[1::2]))


def resolve(value, pointer):
    if not pointer:
        return value
    for part in pointer.lstrip('/').split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def walk_strings(value, pointer=''):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk_strings(item, pointer + '/' + str(i))
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, pointer + '/' + key.replace('~', '~0').replace('/', '~1'))


def render_decision(args):
    return '\n'.join([
        '**Rating**: ' + args['rating'], '',
        '**Executive Summary**: ' + args['executive_summary'], '',
        '**Investment Thesis**: ' + args['investment_thesis'], '',
        '**Price Target**: ' + str(args['price_target'] if args['price_target'] is not None else 'not provided'), '',
        '**Time Horizon**: ' + (args['time_horizon'] or 'not provided'),
    ])


def render_plan(args):
    return '\n'.join(['**Recommendation**: '+args['recommendation'], '', '**Rationale**: '+args['rationale'],
                      '', '**Strategic Actions**: '+args['strategic_actions']])


def render_trader(args):
    parts = ['**Action**: '+args['action'], '', '**Reasoning**: '+args['reasoning']]
    for label, key in [('Entry Price','entry_price'),('Stop Loss','stop_loss'),('Position Sizing','position_sizing')]:
        value = args.get(key)
        parts.extend(['', '**'+label+'**: '+str(value if value is not None and value!='' else 'not provided')])
    return '\n'.join(parts+['', 'FINAL TRANSACTION PROPOSAL: **'+args['action'].upper()+'**'])


RENDERERS = {
    'final_trade_decision': ('PortfolioDecision','render_portfolio_decision_v1',render_decision),
    'investment_plan': ('ResearchPlan','render_research_plan_v1',render_plan),
    'trader_investment_plan': ('TraderProposal','render_trader_proposal_v1',render_trader),
}


def matches(text, quote):
    pos = 0
    while True:
        pos = text.find(quote, pos)
        if pos < 0:
            return
        yield pos, pos + len(quote)
        pos += max(1, len(quote))


def decode_envelope(text, evidence, fixture):
    """Validate content identity only. A self-supplied digest conveys no source authority."""
    encoded = text
    wrapper = re.fullmatch(r'\[([A-Za-z_][A-Za-z_0-9]*) returned\]\n(.*)',text,re.S)
    transform = 'json_parse:/evidence/content'
    if wrapper:
        encoded = wrapper.group(2)
        transform = 'tool_return_prefix_then_json_parse:/evidence/content'
    try:
        envelope = json.loads(encoded)
    except (ValueError, TypeError):
        if encoded.lstrip().startswith('{') and '"evidence"' in encoded:
            return dict(status='REJECTED',reason='malformed_json')
        return None
    if not isinstance(envelope,dict) or 'evidence' not in envelope:
        return None
    item = envelope['evidence']
    if not isinstance(item,dict):
        return dict(status='REJECTED',reason='invalid_item_shape')
    known = next((e for e in evidence if e['evidence_key']==item.get('evidence_id')),None)
    if not known:
        return dict(status='REJECTED',reason='unknown_evidence_id')
    if not isinstance(item.get('content'),str) or object_hash(item)!=known['item_hash']:
        return dict(status='REJECTED',reason='item_mismatch')
    if envelope.get('content_hash')!=object_hash(item):
        return dict(status='REJECTED',reason='declared_hash_mismatch')
    if envelope.get('fixture_id')!=fixture['fixture_id'] or envelope.get('fixture_kind')!=fixture['kind'] or envelope.get('provenance')!=fixture['provenance']:
        return dict(status='REJECTED',reason='fixture_wrapper_mismatch')
    if wrapper and wrapper.group(1)!=known['tool']:
        return dict(status='REJECTED',reason='wrapper_tool_mismatch')
    return dict(status='CONTENT_MATCH', envelope=envelope, evidence_id=known['id'],
                item_hash=object_hash(item), declared_hash=envelope['content_hash'], content=item['content'],
                encoded_json=encoded,transform=transform,wrapper_tool=wrapper.group(1) if wrapper else None)


def envelope_lineage(decoded, message, start, events, event_ids):
    """Use recorded role + tool-call ID + whole output equality, never digest alone."""
    exact = []
    verified = []
    retrievals = []
    for event in events:
        if event['run_id']!=start['run_id'] or event['seq']>=start['seq'] or event['kind']!='tool.end':
            continue
        output = event['payload'].get('output',{})
        if not isinstance(output,dict) or output.get('content')!=decoded['encoded_json']:
            continue
        exact.append(event_ids[event['seq']])
        prior = [r for r in events if r['kind']=='evidence.retrieved' and r['run_id']==start['run_id']
                 and r['seq']<event['seq'] and r['payload']==decoded['envelope']]
        if message.get('type')=='tool' and message.get('tool_call_id') and message['tool_call_id']==output.get('tool_call_id') and prior and decoded['wrapper_tool'] is None:
            verified.append(event_ids[event['seq']])
            retrievals += [event_ids[r['seq']] for r in prior]
    mode = 'decoded_tool_result_lineage' if verified else 'decoded_envelope_presence'
    return mode, dict(recorded_role=message.get('type'),input_tool_call_id=message.get('tool_call_id'),
                       item_hash=decoded['item_hash'],envelope_declared_hash=decoded['declared_hash'],
                       wrapper_tool=decoded['wrapper_tool'],input_transform=decoded['transform'],
                       matching_prior_tool_result_ids=exact,verified_tool_result_ids=verified,
                       matching_retrieval_ids=sorted(set(retrievals)),
                       authority='Recorded lineage only; no independent source or real-world accuracy established.')


class Ledger:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.rows = {table: {} for table in TABLES}

    def add(self, table, identity, **values):
        key = ident(table, identity)
        row = dict(table=table, id=key, **VERSIONS, **values)
        expected = {name for name, _ in columns(table)}
        if set(values) != expected:
            raise ValueError((table, expected - set(values), set(values) - expected))
        previous = self.rows[table].get(key)
        if previous is not None and previous != row:
            raise ValueError('Identity collision: ' + key)
        self.rows[table][key] = row
        return key

    def artifact(self, path):
        path = Path(path)
        relative = path.relative_to(self.root).as_posix()
        data = path.read_bytes()
        return self.add('artifacts', [relative, sha(data)], path=relative, sha256=sha(data), bytes=len(data))

    def text(self, artifact, pointer, text, event=None, role=None, transform=None):
        return self.add('texts', [artifact, event, pointer, transform], artifact_id=artifact,
                        event_id=event, pointer=pointer, transform=transform, text=text,
                        sha256=sha(text), role=role)

    def check(self, table, subject, category, method, result, details):
        return self.add('checks', [table, subject, category, method], subject_table=table,
                        subject_id=subject, category=category, method=method, result=result, details=details)

    def all(self):
        return [r for table in sorted(self.rows) for _, r in sorted(self.rows[table].items())]


def origin(events, report, field):
    found = []
    for event in events:
        if event['kind'] != 'llm.end':
            continue
        for i, batch in enumerate(event['payload']['response'].get('generations', [])):
            for j, generation in enumerate(batch):
                base = f'/payload/response/generations/{i}/{j}'
                if generation.get('text') == report:
                    found.append((event, 'exact_generation_text', base + '/text', None))
                elif field in RENDERERS:
                    name, method, renderer = RENDERERS[field]
                    for k, call in enumerate(generation.get('message', {}).get('tool_calls', [])):
                        args = call.get('args', {})
                        if call.get('name') == name and renderer(args) == report:
                            found.append((event, method, base + f'/message/tool_calls/{k}/args', args))
    if len(found) > 1:
        raise ValueError('Ambiguous report origin: ' + field)
    return found[0] if found else (None, 'unresolved', None, None)


def load_run(ledger, directory, session, fixture, fixture_aid, evidence_ids):
    manifest_aid = ledger.artifact(directory / 'run_manifest.json')
    manifest = json.loads((directory / 'run_manifest.json').read_text(encoding='utf-8'))
    ctx = manifest['context']
    run_id = directory.name
    run = ledger.add('runs', run_id, artifact_id=manifest_aid, run_id=run_id, pair_id=ctx['pair_id'],
                     arm=ctx['arm'], model=ctx['model'], fixture_hash=ctx['fixture_hash'],
                     config_hash=manifest['config_hash'], session_config_hash=session['config_hash'])
    if object_hash(fixture) != ctx['fixture_hash']:
        raise ValueError('Fixture hash mismatch')
    if object_hash(manifest['config']) != manifest['config_hash']:
        raise ValueError('Run config hash mismatch')
    raw_aid = ledger.artifact(directory / 'trace.jsonl')
    events = [json.loads(line) for line in (directory / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    previous = None
    event_ids = {}
    for line, event in enumerate(events, 1):
        body = {k: v for k, v in event.items() if k != 'event_hash'}
        if event['seq'] != line or event['run_id'] != run_id or object_hash(body) != event['event_hash'] or body['previous_hash'] != previous:
            raise ValueError(f'Invalid source trace {run_id}:{line}')
        if event['context'] != ctx:
            raise ValueError('Event context differs from manifest')
        key = ledger.add('events', [run_id, event['event_id']], artifact_id=raw_aid,
                         run_id=run_id, seq=line, event_id=event['event_id'], timestamp=event['timestamp'],
                         kind=event['kind'], span_id=event['span_id'], parent_id=event['parent_id'],
                         event_hash=event['event_hash'], raw=event)
        event_ids[event['seq']] = key
        previous = event['event_hash']
        if event['kind'] == 'evidence.available':
            if event['payload'] != fixture:
                raise ValueError('Available fixture differs')
            for evidence_id in evidence_ids.values():
                ledger.add('availability', [run_id, evidence_id, key], run_id=run_id, evidence_id=evidence_id, event_id=key)
        if event['kind'] == 'evidence.retrieved':
            item = event['payload']['evidence']
            eid = evidence_ids[item['evidence_id']]
            if event['payload']['content_hash'] != object_hash(item) or ledger.rows['evidence'][eid]['item_hash'] != object_hash(item):
                raise ValueError('Retrieved item hash differs')
            ledger.add('retrievals', key, run_id=run_id, evidence_id=eid, event_id=key, request=event['payload']['request'])
    sqlite_aid = ledger.artifact(directory / 'trace.sqlite')
    with closing(sqlite3.connect((directory / 'trace.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT seq,event_id,run_id,timestamp,kind,span_id,parent_id,payload_json,event_hash FROM events ORDER BY seq').fetchall()
    expected = [(e['seq'], e['event_id'], run_id, e['timestamp'], e['kind'], e['span_id'], e['parent_id'], e['payload'], e['event_hash']) for e in events]
    actual = [(*r[:7], json.loads(r[7]), r[8]) for r in rows]
    if expected != actual:
        raise ValueError('Raw SQLite differs from JSONL')
    ledger.check('runs', run, 'source_integrity', 'sha256_chain_sqlite_parity_v1', 'PASS',
                 dict(events=len(events), raw_sqlite_artifact_id=sqlite_aid, last_event_hash=previous))
    starts = [e for e in events if e['kind'] == 'llm.start']
    calls_by_span = {}
    for start in starts:
        ends = [e for e in events if e['span_id'] == start['span_id'] and e['kind'] in ('llm.end', 'llm.error')]
        if len(ends) != 1 or ends[0]['seq'] <= start['seq']:
            raise ValueError('Unaccounted/ambiguous model attempt')
        end = ends[0]
        meta = start['payload'].get('metadata', {}).get('metadata', {})
        actor = meta.get('langgraph_checkpoint_ns', '').split(':')[0] or meta.get('langgraph_node', 'unknown')
        cid = ledger.add('calls', [run_id, start['span_id']], run_id=run_id, span_id=start['span_id'], actor=actor,
                         start_event_id=event_ids[start['seq']], end_event_id=event_ids[end['seq']] if end['kind']=='llm.end' else None,
                         error_event_id=event_ids[end['seq']] if end['kind']=='llm.error' else None,
                         status='completed' if end['kind']=='llm.end' else 'error')
        calls_by_span[start['span_id']] = cid
        for batch, messages in enumerate(start['payload'].get('messages', [])):
            for index, message in enumerate(messages):
                content = message.get('content')
                for suffix, text in walk_strings(content):
                    # Content blocks' text only: exclude function arguments/metadata as delivered evidence.
                    if isinstance(content, list) and not suffix.endswith('/text'):
                        continue
                    pointer = f'/payload/messages/{batch}/{index}/content' + suffix
                    tid = ledger.text(raw_aid, pointer, text, event_ids[start['seq']], message.get('type'))
                    # Tool-message content is itself a JSON envelope. Decode its string
                    # value before comparing CSV newlines; lexical JSON escaping is not
                    # evidence absence. Keep the original input string as well.
                    decoded = decode_envelope(text,list(ledger.rows['evidence'].values()),fixture)
                    if decoded:
                        ledger.check('texts',tid,'envelope_content_validation','fixture_envelope_equality_v1',decoded['status'],
                                     {'reason':decoded.get('reason'),'note':'Content identity only; lineage is checked separately.'})
                        if decoded['status']=='CONTENT_MATCH':
                            mode,provenance = envelope_lineage(decoded,message,start,events,event_ids)
                            dtid = ledger.text(raw_aid,pointer,decoded['content'],event_ids[start['seq']],message.get('type'),decoded['transform'])
                            ledger.add('exposures',[cid,dtid,decoded['evidence_id'],0],call_id=cid,text_id=dtid,
                                       evidence_id=decoded['evidence_id'],report_id=None,start=0,end=len(decoded['content']),
                                       quote=decoded['content'],mode=mode,provenance=provenance)
                            continue
                    for eid, item in ledger.rows['evidence'].items():
                        for left, right in matches(text, item['content']):
                            ledger.add('exposures', [cid, tid, eid, left], call_id=cid, text_id=tid,
                                       evidence_id=eid, report_id=None, start=left, end=right,
                                       quote=item['content'], mode='exact_evidence_text_in_message',
                                       provenance={'recorded_role':message.get('type'),'authority':'Identical text only; no tool-origin lineage asserted.'})
    state_aid = ledger.artifact(directory / 'final_state.json')
    state = json.loads((directory / 'final_state.json').read_text(encoding='utf-8'))
    for field in FIELDS:
        report = state.get(field)
        if not report:
            continue
        tid = ledger.text(state_aid, '/' + field, report, role='report')
        out, method, pointer, args = origin(events, report, field)
        cid = calls_by_span[out['span_id']] if out else None
        rid = ledger.add('reports', [run_id, field], run_id=run_id, field=field, text_id=tid,
                         call_id=cid, output_event_id=event_ids[out['seq']] if out else None,
                         origin_method=method, origin_pointer=pointer, origin_args=args)
        if out:
            ledger.check('reports', rid, 'source_alignment', method, 'PASS',
                         dict(output_seq=out['seq'], input_seq=next(e['seq'] for e in starts if e['span_id']==out['span_id']),
                              note='Exact whole-report equality; does not verify report claims.'))
        if field == 'market_report' and cid:
            call = ledger.rows['calls'][cid]
            start = ledger.rows['events'][call['start_event_id']]
            inputs = '\n'.join(t['text'] for t in ledger.rows['texts'].values() if t['event_id']==call['start_event_id'])
            required = 'Before writing the final report, call get_verified_market_snapshot' in inputs
            snapshots = [r for r in ledger.rows['retrievals'].values() if r['run_id']==run_id
                         and ledger.rows['evidence'][r['evidence_id']]['evidence_key']=='E_SNAPSHOT'
                         and ledger.rows['events'][r['event_id']]['seq'] < start['seq']]
            ledger.check('reports', rid, 'required_tool_compliance', 'snapshot_before_market_report_v1',
                         'PASS' if required and snapshots else 'FAIL' if required else 'UNRESOLVED',
                         dict(instruction_found=required, retrieved_before_input=bool(snapshots),
                              retrieval_ids=[r['id'] for r in snapshots], input_event_id=start['id'],
                              note='Protocol only. CSV may support numbers independently of snapshot-tool compliance.'))
    return events


def add_report_exposures(ledger):
    for call in ledger.rows['calls'].values():
        for text in list(ledger.rows['texts'].values()):
            if text['event_id'] != call['start_event_id']:
                continue
            start = ledger.rows['events'][call['start_event_id']]
            for report in ledger.rows['reports'].values():
                if report['run_id'] != call['run_id'] or not report['output_event_id']:
                    continue
                end = ledger.rows['events'][report['output_event_id']]
                if end['seq'] >= start['seq']:
                    continue
                quote = ledger.rows['texts'][report['text_id']]['text']
                for left, right in matches(text['text'], quote):
                    ledger.add('exposures', [call['id'], text['id'], report['id'], left], call_id=call['id'],
                               text_id=text['id'], evidence_id=None, report_id=report['id'],
                               start=left, end=right, quote=quote, mode='exact_prior_report',
                               provenance={'authority':'Complete prior report text in this input; underlying evidence delivery is separate.'})


def add_mentions(ledger):
    for report in ledger.rows['reports'].values():
        text = ledger.rows['texts'][report['text_id']]['text']
        for evidence in ledger.rows['evidence'].values():
            markers = [(evidence['evidence_key'], 'literal_id')]
            markers += [(m.group(), 'uri') for m in re.finditer(r'fixture://news/[a-z-]+', evidence['content'])]
            for marker, form in markers:
                for start, end in matches(text, marker):
                    # Identifier boundaries prevent an ID substring from counting as a citation.
                    if form == 'literal_id' and ((start and re.match(r'\w', text[start-1])) or (end < len(text) and re.match(r'\w', text[end]))):
                        continue
                    ledger.add('mentions', [report['id'], evidence['id'], start, form], report_id=report['id'],
                               evidence_id=evidence['id'], start=start, end=end, quote=marker, form=form)


def add_assertions(ledger, profile):
    from .selections import select
    for report in ledger.rows['reports'].values():
        text = ledger.rows['texts'][report['text_id']]['text']
        for selection in select(report, text, profile):
            scope = selection.get('scope', 'synthetic_fixture')
            if scope == 'this_run':
                scope = report['run_id']
            elif scope == 'synthetic_fixture':
                scope = 'fixture:'+next(r['fixture_hash'] for r in ledger.rows['runs'].values() if r['run_id']==report['run_id'])
            proposition = dict(entity=selection.get('entity', 'ETH-USD'), predicate=selection['predicate'],
                               value=selection['value'], unit=selection.get('unit'), valid_time=selection.get('valid_time', {'as_of':'2026-10-28'}),
                               scope=scope, modality=selection['modality'], assumptions=selection.get('assumptions', []),
                               identity_status='candidate_equivalence_awaiting_adjudication')
            pid = ledger.add('propositions', proposition, **proposition)
            cid = report['call_id']
            call = ledger.rows['calls'].get(cid)
            event = ledger.rows['events'].get(report['output_event_id'])
            aid = ledger.add('assertions', [report['id'], selection['start'], selection['end'], pid],
                             run_id=report['run_id'], report_id=report['id'], proposition_id=pid,
                             call_id=cid, actor=call['actor'] if call else None, output_event_id=report['output_event_id'],
                             asserted_at=event['timestamp'] if event else None, start=selection['start'], end=selection['end'],
                             quote=text[selection['start']:selection['end']], rule_id=selection['rule'],
                             annotation_status='worker_candidate_awaiting_independent_adjudication')
            for key in selection.get('evidence', []):
                evidence = next(e for e in ledger.rows['evidence'].values() if e['evidence_key']==key)
                ledger.add('links', [aid, evidence['id'], 'support_candidate'], assertion_id=aid, evidence_id=evidence['id'],
                           report_id=None, relation='support_candidate', status='extractor-proposed',
                           basis='Versioned worker selection; not adjudicated factual support.', mention_id=None)
            left = text.rfind('\n', 0, selection['start']) + 1
            right = text.find('\n', selection['end'])
            if right == -1:
                right = len(text)
            for mention in ledger.rows['mentions'].values():
                if mention['report_id']==report['id'] and left <= mention['start'] < right:
                    ledger.add('links', [aid, mention['id']], assertion_id=aid, evidence_id=mention['evidence_id'],
                               report_id=None, relation='same_line_reference', status='agent-asserted',
                               basis='Marker in same line only; attachment and factual support remain unresolved.', mention_id=mention['id'])
            if cid:
                available = [x['id'] for x in ledger.rows['exposures'].values() if x['call_id']==cid]
                ledger.check('assertions', aid, 'recorded_context', 'exact_input_exposures_v1', 'OBSERVED',
                             dict(exposure_ids=available, note='Input presence only, not private reliance or truth.'))
            if selection.get('check'):
                check_selection(ledger, aid, selection)


def check_selection(ledger, assertion_id, selection):
    import csv
    import io
    from decimal import Decimal
    evidence = next(e for e in ledger.rows['evidence'].values() if e['evidence_key']=='E_PRICE')
    data = list(csv.DictReader(io.StringIO(evidence['content'].split('\n', 1)[1])))
    kind = selection['check']
    if kind == 'csv_value':
        row = next(r for r in data if r['Date']==selection['valid_time']['date'])
        observed = row[selection['predicate'].capitalize()]
        passed = Decimal(observed)==Decimal(selection['value'])
    elif kind == 'increasing':
        observed = [r[selection['column']] for r in data]
        passed = all(Decimal(a)<Decimal(b) for a,b in zip(observed, observed[1:]))
    elif kind == 'range_increasing':
        observed = [str(Decimal(r['High'])-Decimal(r['Low'])) for r in data]
        passed = all(Decimal(a)<Decimal(b) for a,b in zip(observed, observed[1:]))
    elif kind == 'below_open':
        observed = [data[-1]['Close'],data[-1]['Open']]
        passed = Decimal(observed[0])<Decimal(observed[1])
    elif kind == 'below_previous_close':
        observed = [data[-1]['Close'],data[-2]['Close']]
        passed = Decimal(observed[0])<Decimal(observed[1])
    else:
        raise ValueError(kind)
    assertion = ledger.rows['assertions'][assertion_id]
    delivered = [x['id'] for x in ledger.rows['exposures'].values() if x['call_id']==assertion['call_id'] and x['evidence_id']==evidence['id'] and x['mode'] in ('decoded_tool_result_lineage','decoded_envelope_presence')]
    ledger.check('assertions', assertion_id, 'conditional_fixture_comparison', 'decimal_' + kind + '_v1',
                 'MATCH' if passed else 'MISMATCH', dict(observed=observed, normalized_value=selection['value'],
                 evidence_id=evidence['id'], recorded_csv_exposure_ids=delivered,
                 precondition='Worker semantic mapping must be independently adjudicated; result is conditional on that mapping.',
                 note='Synthetic fixture only; neither real-world truth nor independent corroboration.'))


def schema_document():
    defs = {}
    for table in TABLES:
        props = {'table': {'const': table}, 'id': {'type': 'string'}}
        props.update({k: {'const': v} for k,v in VERSIONS.items()})
        for name, kind in columns(table):
            types = ['integer' if kind=='INTEGER' else 'string']
            if name in NULLABLE.get(table,set()):
                types.append('null')
            props[name] = {} if kind=='JSON' else {'type': types}
            if (table,name) in ENUMS:
                props[name] = {'enum':sorted(ENUMS[table,name])}
        defs[table] = dict(type='object', properties=props, required=list(props), additionalProperties=False)
    return {'$schema':'https://json-schema.org/draft/2020-12/schema', '$id':'urn:trustkernel:atomic-ledger:'+VERSION,
            'oneOf':[{'$ref':'#/$defs/'+t} for t in TABLES], '$defs':defs}


def validate_rows(rows):
    by = {t:{} for t in TABLES}
    for row in rows:
        table = row.get('table')
        if table not in TABLES or row.get('id') in by[table]:
            raise ValueError('Invalid table or duplicate ID')
        required = {'table','id',*VERSIONS,*(n for n,_ in columns(table))}
        if set(row)!=required or any(row.get(k)!=v for k,v in VERSIONS.items()):
            raise ValueError('Invalid fields/version')
        for name, kind in columns(table):
            value = row[name]
            if value is None and name not in NULLABLE.get(table,set()):
                raise ValueError('Missing required value: '+table+'.'+name)
            if value is not None and kind!='JSON' and not isinstance(value, int if kind=='INTEGER' else str):
                raise ValueError('Invalid column type')
            if (table,name) in ENUMS and value not in ENUMS[table,name]:
                raise ValueError('Invalid vocabulary: '+table+'.'+name)
        by[table][row['id']] = row
    for table, items in by.items():
        for row in items.values():
            for name, _ in columns(table):
                target = FK.get(name)
                # Raw event UUID is deliberately distinct from derived event row ID.
                if table=='events' and name=='event_id':
                    continue
                if target and row[name] is not None and row[name] not in by[target]:
                    raise ValueError(f'Orphan reference {table}.{name}')
            if table in ('assertions', 'mentions', 'exposures'):
                tid = row.get('text_id') or by['reports'][row['report_id']]['text_id']
                text = by['texts'][tid]['text']
                if not (0<=row['start']<row['end']<=len(text)) or text[row['start']:row['end']]!=row['quote']:
                    raise ValueError('Invalid exact text span')
            if 'run_id' in row and table!='runs' and row['run_id'] not in {r['run_id'] for r in by['runs'].values()}:
                raise ValueError('Unknown run')
            if table=='checks' and row['subject_id'] not in by.get(row['subject_table'], {}):
                raise ValueError('Orphan check subject')
            if table=='checks' and row['method']=='exact_input_exposures_v1':
                assertion = by['assertions'][row['subject_id']]
                expected = sorted(e['id'] for e in by['exposures'].values() if e['call_id']==assertion['call_id'])
                if sorted(row['details']['exposure_ids'])!=expected:
                    raise ValueError('Missing/mismatched exposure inventory')
            if table=='assertions':
                report = by['reports'][row['report_id']]
                if row['run_id']!=report['run_id'] or row['call_id']!=report['call_id'] or row['output_event_id']!=report['output_event_id']:
                    raise ValueError('Assertion origin mismatch')
            if table=='exposures':
                call = by['calls'][row['call_id']]
                if by['texts'][row['text_id']]['event_id'] != call['start_event_id']:
                    raise ValueError('Exposure not in this model input')
                if (row['evidence_id'] is None)==(row['report_id'] is None):
                    raise ValueError('Exposure must identify exactly one evidence item or report')
                if row['evidence_id'] and row['quote'] != by['evidence'][row['evidence_id']]['content']:
                    raise ValueError('Exposure content differs')
                if row['report_id']:
                    report = by['reports'][row['report_id']]
                    if row['quote']!=by['texts'][report['text_id']]['text']:
                        raise ValueError('Report exposure is not complete report text')
                    if report['run_id']!=call['run_id'] or by['events'][report['output_event_id']]['seq']>=by['events'][call['start_event_id']]['seq']:
                        raise ValueError('Report exposure precedes report or crosses run')
            if table=='events':
                raw = row['raw']
                if object_hash({k:v for k,v in raw.items() if k!='event_hash'})!=row['event_hash']:
                    raise ValueError('Invalid event hash')
                for name in ('run_id','seq','event_id','timestamp','kind','span_id','parent_id','event_hash'):
                    if row[name]!=raw[name]:
                        raise ValueError('Normalized event differs from raw event')
            if table=='retrievals':
                event = by['events'][row['event_id']]
                if event['kind']!='evidence.retrieved' or event['run_id']!=row['run_id']:
                    raise ValueError('Retrieval source mismatch')
            if table=='calls':
                start = by['events'][row['start_event_id']]
                end_id = row['end_event_id'] or row['error_event_id']
                if not end_id or bool(row['end_event_id'])==bool(row['error_event_id']):
                    raise ValueError('Call must have exactly one terminal event')
                end = by['events'][end_id]
                if start['kind']!='llm.start' or start['seq']>=end['seq'] or start['span_id']!=end['span_id'] or start['run_id']!=row['run_id'] or end['run_id']!=row['run_id']:
                    raise ValueError('Invalid call temporal/span link')
    for run in by['runs'].values():
        previous = None
        for seq,event in enumerate(sorted((e for e in by['events'].values() if e['run_id']==run['run_id']),key=lambda e:e['seq']),1):
            if event['seq']!=seq or event['raw']['previous_hash']!=previous:
                raise ValueError('Invalid event chain/order')
            previous = event['event_hash']
    return by


def validate_sources(rows, root=ROOT):
    by = validate_rows(rows)
    parsed = {}
    for aid, row in by['artifacts'].items():
        path = (Path(root) / row['path']).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            raise ValueError('Artifact escapes project root')
        data = path.read_bytes()
        if len(data)!=row['bytes'] or sha(data)!=row['sha256']:
            raise ValueError('Source artifact changed: '+row['path'])
        if path.suffix=='.json':
            parsed[aid] = json.loads(data)
        elif path.suffix=='.jsonl':
            parsed[aid] = [json.loads(line) for line in data.decode('utf-8').splitlines()]
    for row in by['events'].values():
        if parsed[row['artifact_id']][row['seq']-1]!=row['raw']:
            raise ValueError('Event source mismatch')
    for row in by['texts'].values():
        source = by['events'][row['event_id']]['raw'] if row['event_id'] else parsed[row['artifact_id']]
        value = resolve(source,row['pointer'])
        if row['transform']=='json_parse:/evidence/content':
            value = resolve(json.loads(value),'/evidence/content')
        elif row['transform']=='tool_return_prefix_then_json_parse:/evidence/content':
            wrapper = re.fullmatch(r'\[([A-Za-z_][A-Za-z_0-9]*) returned\]\n(.*)',value,re.S)
            if not wrapper:
                raise ValueError('Invalid tool-return wrapper transformation')
            value = resolve(json.loads(wrapper.group(2)),'/evidence/content')
        elif row['transform'] is not None:
            raise ValueError('Unknown source text transformation')
        if value!=row['text'] or sha(row['text'])!=row['sha256']:
            raise ValueError('Text source mismatch')
    for report in by['reports'].values():
        if report['output_event_id']:
            event = by['events'][report['output_event_id']]
            value = resolve(event['raw'], report['origin_pointer'])
            original = by['texts'][report['text_id']]['text']
            renderer = next((v[2] for v in RENDERERS.values() if v[1]==report['origin_method']),None)
            if renderer:
                value = renderer(value)
                if resolve(event['raw'],report['origin_pointer'])!=report['origin_args']:
                    raise ValueError('Stored report origin arguments differ')
            if value!=original:
                raise ValueError('Report source mismatch')
            call = by['calls'][report['call_id']]
            if call['end_event_id']!=event['id'] or by['events'][call['start_event_id']]['seq']>=event['seq']:
                raise ValueError('Report temporal origin mismatch')
    for exposure in by['exposures'].values():
        if exposure['mode'] in ('decoded_tool_result_lineage','decoded_envelope_presence'):
            text = by['texts'][exposure['text_id']]
            if text['transform'] not in ('json_parse:/evidence/content','tool_return_prefix_then_json_parse:/evidence/content'):
                raise ValueError('Decoded evidence exposure lacks transformation')
            encoded_input = resolve(by['events'][text['event_id']]['raw'],text['pointer'])
            fixture_artifact = by['artifacts'][by['evidence'][exposure['evidence_id']]['artifact_id']]
            fixture = parsed[fixture_artifact['id']]
            decoded = decode_envelope(encoded_input,list(by['evidence'].values()),fixture)
            if not decoded or decoded['status']!='CONTENT_MATCH':
                raise ValueError('Decoded evidence no longer matches known content')
            envelope = decoded['envelope']
            item = by['evidence'][exposure['evidence_id']]
            if object_hash(envelope['evidence'])!=item['item_hash'] or envelope.get('content_hash')!=item['item_hash']:
                raise ValueError('Delivered evidence hash mismatch')
            call = by['calls'][exposure['call_id']]
            start = by['events'][call['start_event_id']]
            source_event = by['events'][text['event_id']]['raw']
            message_pointer = text['pointer'].rsplit('/content',1)[0]
            message = resolve(source_event,message_pointer)
            raw_events = [e['raw'] for e in by['events'].values() if e['run_id']==call['run_id']]
            ids = {e['seq']:e['id'] for e in by['events'].values() if e['run_id']==call['run_id']}
            mode,provenance = envelope_lineage(decoded,message,start['raw'],raw_events,ids)
            if mode!=exposure['mode'] or provenance!=exposure['provenance']:
                raise ValueError('Envelope lineage mismatch')
    return by


def rebuild(rows, path):
    by = validate_rows(rows)
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    if temporary.exists():
        temporary.unlink()
    with closing(sqlite3.connect(temporary)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        for table in TABLES:
            fields = ['id TEXT PRIMARY KEY', 'schema_version TEXT NOT NULL', 'normalization_version TEXT NOT NULL', 'extraction_version TEXT NOT NULL']
            constraints = []
            for name, kind in columns(table):
                required = ' NOT NULL' if name not in NULLABLE.get(table,set()) else ''
                fields.append(name + ' ' + ('TEXT' if kind=='JSON' else kind) + required)
                if name in FK and not (table=='events' and name=='event_id'):
                    constraints.append(f'FOREIGN KEY({name}) REFERENCES {FK[name]}(id) DEFERRABLE INITIALLY DEFERRED')
                if name=='run_id' and table!='runs':
                    constraints.append('FOREIGN KEY(run_id) REFERENCES runs(run_id) DEFERRABLE INITIALLY DEFERRED')
            if table=='runs':
                constraints.append('UNIQUE(run_id)')
            db.execute(f'CREATE TABLE {table} (' + ','.join(fields + constraints) + ')')
        with db:
            for table, items in by.items():
                names = ['id',*VERSIONS,*(name for name,_ in columns(table))]
                json_names = {name for name,kind in columns(table) if kind=='JSON'}
                db.executemany(f'INSERT INTO {table} ('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')',
                               [[canonical(row[n]) if n in json_names else row[n] for n in names] for row in items.values()])
            db.execute('CREATE TABLE ledger_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            normalized = ''.join(canonical(r)+'\n' for r in sorted(rows,key=lambda r:(r['table'],r['id'])))
            db.execute('INSERT INTO ledger_metadata VALUES (?,?)',('canonical_sha256',sha(normalized)))
        db.executescript('''
CREATE INDEX events_run_seq ON events(run_id,seq);
CREATE INDEX calls_run_actor ON calls(run_id,actor);
CREATE INDEX assertions_proposition ON assertions(proposition_id);
CREATE INDEX exposures_call ON exposures(call_id);
CREATE VIEW assertion_details AS SELECT a.*, r.field, p.entity,p.predicate,p.value,p.unit,p.valid_time,p.scope,p.modality FROM assertions a JOIN reports r ON r.id=a.report_id JOIN propositions p ON p.id=a.proposition_id;
CREATE VIEW evidence_stages AS SELECT r.run_id,e.id evidence_id,e.evidence_key,
 (SELECT COUNT(*) FROM availability x WHERE x.run_id=r.run_id AND x.evidence_id=e.id) available,
 (SELECT COUNT(*) FROM retrievals x WHERE x.run_id=r.run_id AND x.evidence_id=e.id) retrieved,
 (SELECT COUNT(*) FROM exposures x JOIN calls c ON c.id=x.call_id WHERE c.run_id=r.run_id AND x.evidence_id=e.id) exact_deliveries,
 (SELECT COUNT(*) FROM mentions x JOIN reports p ON p.id=x.report_id WHERE p.run_id=r.run_id AND x.evidence_id=e.id) report_mentions
 FROM runs r CROSS JOIN evidence e;
''')
        if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('SQLite integrity failure')
    temporary.replace(path)


def validate_index(rows, path):
    by = validate_rows(rows)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Index integrity failure')
        normalized = ''.join(canonical(r)+'\n' for r in sorted(rows,key=lambda r:(r['table'],r['id'])))
        if db.execute("SELECT value FROM ledger_metadata WHERE key='canonical_sha256'").fetchone()!=(sha(normalized),):
            raise ValueError('Index belongs to another canonical build')
        for table in TABLES:
            names = ['id',*VERSIONS,*(n for n,_ in columns(table))]
            json_names = {n for n,k in columns(table) if k=='JSON'}
            stored = db.execute('SELECT '+','.join(names)+' FROM '+table+' ORDER BY id').fetchall()
            expected = [tuple(canonical(r[n]) if n in json_names else r[n] for n in names) for _,r in sorted(by[table].items())]
            if stored!=expected:
                raise ValueError('Index rows differ: '+table)


def validate_bundle(profile, root=ROOT):
    destination = Path(root)/'verification/data'/profile
    data = (destination/'ledger.jsonl').read_bytes()
    rows = [json.loads(line) for line in data.decode('utf-8').splitlines()]
    manifest = json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
    coverage_bytes = (destination/'coverage.json').read_bytes()
    summary = json.loads(coverage_bytes)
    if sha(data)!=manifest['canonical_sha256'] or sha(coverage_bytes)!=manifest['coverage_sha256']:
        raise ValueError('Bundle hashes mismatch; incomplete or altered build')
    if manifest['build_id']!=summary['build_id'] or summary['canonical_sha256']!=sha(data):
        raise ValueError('Mixed build snapshots')
    counts = dict(Counter(r['table'] for r in rows))
    if len(rows)!=manifest['rows'] or counts!=manifest['counts'] or counts!=summary['counts']:
        raise ValueError('Bundle row counts mismatch')
    for path,digest in manifest['implementation_hashes'].items():
        if sha((Path(root)/path).read_bytes())!=digest:
            raise ValueError('Implementation changed since build: '+path)
    validate_sources(rows,root)
    validate_index(rows,destination/'ledger.sqlite')
    return rows,manifest


def coverage(ledger, profile):
    reports = []
    for report in ledger.rows['reports'].values():
        text = ledger.rows['texts'][report['text_id']]['text']
        assertions = [a for a in ledger.rows['assertions'].values() if a['report_id']==report['id']]
        covered = set()
        for a in assertions:
            covered.update(range(a['start'], a['end']))
        reports.append(dict(run_id=report['run_id'], field=report['field'], characters=len(text),
                            selected_assertions=len(assertions), selected_unique_characters=len(covered),
                            unselected_characters=len(text)-len(covered), origin=report['origin_method']))
    return dict(profile=profile, versions=VERSIONS, counts={t:len(v) for t,v in ledger.rows.items()}, reports=reports,
                independent_reference_set=False, semantic_recall=None, quality_score=None,
                omissions=['Investment/trader plans, bull/bear/risk dialogue are preserved but not atomized.',
                           'Market/news/final fields have selected spans only; all other text remains unselected.',
                           'General knowledge, conditional guidance, paraphrased evidence delivery and causal dependencies are not exhaustively extracted.',
                           'Semantic mappings/equivalence/support links require independent adjudication.'],
                check_results=dict(Counter(c['category']+':'+c['result'] for c in ledger.rows['checks'].values())))


def build(profile='full', session_dir=SESSION):
    session_dir = Path(session_dir)
    ledger = Ledger()
    session_aid = ledger.artifact(session_dir / 'experiment.json')
    ledger.artifact(session_dir / 'analysis.json')
    ledger.artifact(session_dir / 'review_packets.json')
    ledger.artifact(ROOT/'upstream/tradingagents/tradingagents/agents/schemas.py')
    session = json.loads((session_dir / 'experiment.json').read_text(encoding='utf-8'))
    fixture_aid = ledger.artifact(session_dir / 'fixture.json')
    fixture = json.loads((session_dir / 'fixture.json').read_text(encoding='utf-8'))
    evidence_ids = {}
    for tool, item in fixture['tools'].items():
        key = item['evidence_id']
        status = 'NO_DATA' if key in ('E_INDICATOR','E_MACRO','E_PREDICTION') else 'PARTIAL' if key=='E_SNAPSHOT' else 'CONTENT'
        evidence_ids[key] = ledger.add('evidence', [session['fixture_hash'],key,object_hash(item)], artifact_id=fixture_aid,
                                      pointer='/tools/'+tool, fixture_hash=session['fixture_hash'], evidence_key=key, tool=tool,
                                      item_hash=object_hash(item), content=item['content'], content_status=status,
                                      observed_at=item.get('observed_at'), source_id=item.get('source_id'), root_source_id=item.get('root_source_id'),
                                      provider=fixture['provenance']['provider'], scope=fixture['kind'])
    for directory in sorted(session_dir.iterdir()):
        if not (directory / 'trace.jsonl').exists():
            continue
        manifest = json.loads((directory/'run_manifest.json').read_text(encoding='utf-8'))
        if profile=='pilot' and not manifest['context']['pair_id'].endswith('-pair-0'):
            continue
        load_run(ledger, directory, session, fixture, fixture_aid, evidence_ids)
    add_report_exposures(ledger)
    add_mentions(ledger)
    add_assertions(ledger, profile)
    rows = ledger.all()
    validate_sources(rows)
    destination = ROOT / 'verification/data' / profile
    destination.mkdir(parents=True,exist_ok=True)
    content = ''.join(canonical(row)+'\n' for row in rows)
    (destination/'ledger.jsonl').write_text(content,encoding='utf-8',newline='\n')
    rebuild(rows, destination/'ledger.sqlite')
    summary = coverage(ledger, profile)
    code_paths = sorted((ROOT/'verification').glob('*.py'))+[ROOT/'verification/CONTRACT.md',ROOT/'verification/tests/test_ledger.py']
    implementation_hashes = {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in code_paths}
    build_id = profile+'-'+sha(canonical(dict(canonical_sha256=sha(content),implementation_hashes=implementation_hashes)))[:20]
    summary.update(build_id=build_id,canonical_sha256=sha(content))
    summary_text = json.dumps(summary,indent=2,ensure_ascii=False)+'\n'
    (destination/'coverage.json').write_text(summary_text,encoding='utf-8',newline='\n')
    manifest = dict(versions=VERSIONS,profile=profile, source_root=str(ROOT),session_artifact_id=session_aid,
                    build_id=build_id,canonical_sha256=sha(content),coverage_sha256=sha(summary_text),rows=len(rows),counts=summary['counts'],
                    source_artifacts=list(ledger.rows['artifacts'].values()),
                    implementation_hashes=implementation_hashes,
                    network_calls=0,model_calls=0,independent_semantic_gold=False)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    lines = [f'# {profile.title()} build snapshot', '', 'Exploratory draft. This file is generated with its ledger and coverage.', '',
             f'Build ID: `{build_id}`', '', f'Canonical JSONL SHA-256: `{sha(content)}`', '',
             '| Table | Rows |', '|---|---:|']
    lines += [f'| {table} | {count} |' for table,count in summary['counts'].items()]
    lines += ['', '| Check category/result | Rows |', '|---|---:|']
    lines += [f'| {key} | {count} |' for key,count in summary['check_results'].items()]
    lines += ['', 'All report origins are exact whole-text or structured-format matches. Assertions are selected worker candidates, not independent labels.',
              'Exposure modes distinguish decoded envelopes with recorded tool-call lineage, envelope presence alone, exact evidence text in prose, and complete prior reports.',
              'Counts refer only to this build. Regeneration replaces the current profile; compare build IDs before combining reports.', '']
    (destination/'BUILD.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    (ROOT/'verification/schema.json').write_text(json.dumps(schema_document(),indent=2)+'\n',encoding='utf-8',newline='\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    b = sub.add_parser('build'); b.add_argument('--profile',choices=['pilot','full'],default='full')
    for name in ('validate','rebuild'):
        p = sub.add_parser(name);p.add_argument('--profile',choices=['pilot','full'],default='full')
    args = parser.parse_args()
    if args.command=='build':
        summary = build(args.profile)
        print(json.dumps({'profile':args.profile,'counts':summary['counts'],'checks':summary['check_results']},indent=2))
    else:
        destination = ROOT/'verification/data'/args.profile
        rows = [json.loads(line) for line in (destination/'ledger.jsonl').read_text(encoding='utf-8').splitlines()]
        if args.command=='rebuild':
            rebuild(rows,destination/'ledger.sqlite')
        else:
            rows,manifest = validate_bundle(args.profile)
            print('build_id: '+manifest['build_id'])
        print(args.command + ': PASS, ' + str(len(rows)) + ' rows')


if __name__=='__main__':
    main()
