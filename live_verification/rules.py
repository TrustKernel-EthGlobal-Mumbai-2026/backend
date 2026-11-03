"""Deterministic, scoped findings over the new canonical live ledger only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from . import rules_checks as ck

VERSION = 'live-ledger-rules-0.1'
POLICY_VERSION = 'live-ledger-policy-0.1'
STATUSES = {'PASS', 'FAIL', 'INCONCLUSIVE', 'ERROR', 'NOT_APPLICABLE'}
LIMITS = [
    'Findings concern recorded strings, scoped protocol or arithmetic; no global clearance.',
    'Input presence is not private reliance, trusted tool lineage or semantic entailment.',
    'No source fetch, model call, feedback, historical repair or decision intervention occurred.',
    'No independent semantic accuracy benchmark, model ranking or identical-source control.',
]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def finding(rule, status, run_id, reason, expected, observed, *, refs=(), candidates=(),
            spans=(), scope=None, coverage=None, limits=()):
    if status not in STATUSES:
        raise ValueError('unknown finding status')
    row = dict(rule_id=rule, status=status, run_id=run_id, reason_code=reason,
               scope=scope or rule, method_version=VERSION, policy_version=POLICY_VERSION,
               expected=expected, observed=observed,
               source_refs=sorted(refs, key=canonical), candidate_refs=sorted(candidates, key=canonical),
               span_refs=sorted(spans, key=canonical), coverage=coverage or {},
               limitations=list(LIMITS)+list(limits))
    row['finding_id'] = 'live-finding:'+digest(row)
    return row


class Context:
    def __init__(self, rows):
        self.rows = list(rows)
        self.tables = defaultdict(list)
        self.ids = {}
        self._inputs_cache = {}
        self._exposure_cache = {}
        self._scalar_cache = {}
        for row in self.rows:
            if not isinstance(row, dict) or not all(k in row for k in ('id', 'table', 'run_id')):
                raise ValueError('canonical row schema invalid')
            if row['id'] in self.ids:
                raise ValueError('duplicate canonical row id')
            self.ids[row['id']] = row
            self.tables[row['table']].append(row)
        for rows in self.tables.values():
            rows.sort(key=lambda r:r['id'])

    def rows_for(self, table, run_id):
        return [r for r in self.tables[table] if r['run_id'] == run_id]

    def get(self, identity, table=None):
        row = self.ids.get(identity)
        if row is None or table is not None and row['table'] != table:
            return None
        return row

    def ref(self, row, start=None, end=None):
        out = {k:row[k] for k in ('id', 'table', 'run_id')}
        for k in ('artifact_id', 'event_id', 'text_id', 'call_id', 'pointer', 'sha256', 'seq'):
            if row.get(k) is not None:
                out[k] = row[k]
        if start is not None or end is not None:
            value = row.get('text', row.get('content'))
            if not isinstance(value, str) or type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(value):
                raise ValueError('invalid canonical span binding')
            out.update(start=start, end=end, quote=value[start:end], text_sha256=text_hash(value))
        return out

    def raw(self, event):
        raw = event.get('raw')
        if not isinstance(raw, dict):
            raise ValueError('canonical event lacks raw event')
        return raw

    def report_call(self, report):
        text = self.get(report.get('text_id'), 'texts')
        call = self.get(report.get('call_id'), 'calls')
        if call is None and text:
            call = self.get(text.get('call_id'), 'calls')
        if call and call['run_id'] != report['run_id']:
            raise ValueError('cross-run report origin')
        return text, call

    def inputs(self, call):
        if call['id'] in self._inputs_cache:
            return self._inputs_cache[call['id']]
        result = []
        for text in self.rows_for('texts', call['run_id']):
            if text.get('call_id') != call['id']:
                continue
            event = self.get(text.get('event_id'), 'events')
            if event and event.get('kind') == 'llm.start':
                result.append(text)
        self._inputs_cache[call['id']] = result
        return result

    def exposed_sources(self, call):
        if call['id'] in self._exposure_cache:
            return self._exposure_cache[call['id']]
        result = []
        for exposure in self.rows_for('exposures', call['run_id']):
            if exposure.get('call_id') != call['id'] or exposure.get('pre_assertion') is not True:
                continue
            source = self.get(exposure.get('source_id'), 'sources')
            if source and source['run_id'] == call['run_id'] and source.get('seq', 10**20) < call.get('input_seq', -1):
                result.append((source, exposure))
        self._exposure_cache[call['id']] = result
        return result

    def source_scalars(self, source):
        if source['id'] not in self._scalar_cache:
            self._scalar_cache[source['id']] = ck.snapshot_scalars(source.get('content', ''))
        return self._scalar_cache[source['id']]


def _actor(raw):
    metadata = raw.get('payload', {}).get('metadata', {}).get('metadata', {})
    checkpoint = metadata.get('langgraph_checkpoint_ns') or metadata.get('checkpoint_ns')
    return checkpoint.split(':', 1)[0] if isinstance(checkpoint, str) else None


def _market(actor):
    return isinstance(actor, str) and actor.lower().replace('_', ' ') == 'market analyst'


def _walk(value, pointer=''):
    yield pointer, value
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace('~', '~0').replace('/', '~1')
            yield from _walk(child, pointer+'/'+escaped)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from _walk(child, pointer+'/'+str(i))


def protocol_findings(ctx, report):
    run_id = report['run_id']; text, call = ctx.report_call(report)
    refs = [ctx.ref(report)]; prompts = []; spans = []
    events = sorted(ctx.rows_for('events', run_id), key=lambda r:r['seq'])
    if not text or not call or not _market(call.get('actor')):
        return [finding('required_snapshot_invocation', 'INCONCLUSIVE', run_id,
                        'REPORT_OR_ACTOR_ORIGIN_UNRESOLVED', 'bound Market Analyst report and actual input',
                        {'report': report['id'], 'origin_status': report.get('origin_status')}, refs=refs)]
    inputs = ctx.inputs(call)
    for item in inputs:
        m = re.search(r'Before writing the final report,\s*call\s+get_verified_market_snapshot\b', item.get('text', ''))
        if m:
            prompts.append(item); spans.append(ctx.ref(item, *m.span()))
    end = ctx.get(call.get('end_event_id'), 'events')
    output_seq = call.get('output_seq')
    prefix = [e for e in events if output_seq is not None and e['seq'] < output_seq]
    complete = bool(end and [e['seq'] for e in prefix] == list(range(1, output_seq)))
    invocations = [e for e in prefix if e['kind'] == 'tool.start'
                   and ctx.raw(e).get('payload', {}).get('tool', {}).get('name') == 'get_verified_market_snapshot']
    known = [e for e in invocations if _market(_actor(ctx.raw(e)))]
    unknown = [e for e in invocations if _actor(ctx.raw(e)) is None]
    status = ('INCONCLUSIVE' if not prompts or not complete or unknown else 'PASS' if known else 'FAIL')
    reason = ('OBLIGATION_OR_PREFIX_OR_ACTOR_UNRESOLVED' if status == 'INCONCLUSIVE'
              else 'REQUIRED_INVOCATION_OBSERVED' if known else 'REQUIRED_INVOCATION_OMITTED')
    sources = [s for s in ctx.rows_for('sources', run_id)
               if s.get('tool') == 'get_verified_market_snapshot' and s.get('seq', 10**20) < (output_seq or -1)]
    refs += [ctx.ref(r) for r in [call, text, *known, *unknown, *sources]]
    if end:
        refs.append(ctx.ref(end))
    findings = [finding('required_snapshot_invocation', status, run_id, reason,
                        'Market Analyst invokes get_verified_market_snapshot before its report',
                        {'report_id': report['id'], 'input_seq': call.get('input_seq'), 'output_seq': output_seq,
                         'prefix_complete': complete, 'invocation_seqs': [e['seq'] for e in known],
                         'unassigned_invocation_seqs': [e['seq'] for e in unknown],
                         'source_result_statuses': [s.get('source_status', 'UNKNOWN') for s in sources]},
                        refs=refs, spans=spans,
                        limits=['Invocation PASS does not mean source success or report support; acknowledgement does not repair omission.'])]
    starts = [e for e in prefix if e['kind'] == 'run.start']
    cap = ctx.raw(starts[0]).get('payload', {}).get('config', {}).get('max_tool_rounds') if starts else None
    joined = '\n'.join(t.get('text', '') for t in inputs)
    spent = bool(re.search(r'tool rounds (?:are )?spent|no tool rounds remain', joined, re.I))
    fallbacks = [e for e in prefix if e['kind'] == 'runtime.log' and re.search(
        r'fallback|tool rounds|no tools', ctx.raw(e).get('payload', {}).get('message', ''), re.I)]
    findings.append(finding('tool_round_fallback_context', 'PASS' if cap is not None else 'INCONCLUSIVE', run_id,
                            'RECORDED_CONTEXT_ONLY' if cap is not None else 'ROUND_CAP_NOT_BOUND',
                            'retain actual cap and fallback independently from snapshot invocation',
                            {'max_tool_rounds': cap, 'spent_rounds_wording_observed': spent,
                             'fallbacks': [{'seq': e['seq'], 'message': ctx.raw(e)['payload'].get('message')} for e in fallbacks]},
                            refs=[ctx.ref(r) for r in [*starts, *fallbacks, *inputs]],
                            limits=['No inferred causal explanation or automatic exemption from the required invocation.']))
    return findings


def report_completeness(ctx, report):
    text, call = ctx.report_call(report)
    end = ctx.get(call.get('end_event_id'), 'events') if call else None
    refs = [ctx.ref(report)]
    statuses = []; details = []
    if end:
        refs.append(ctx.ref(end))
        for ptr, value in _walk(ctx.raw(end).get('payload', {}).get('response', {}), '/payload/response'):
            if not isinstance(value, dict):
                continue
            if value.get('status') in ('incomplete', 'completed', 'failed', 'cancelled'):
                statuses.append(value['status']); details.append({'pointer': ptr+'/status', 'value': value['status']})
            if value.get('finish_reason') in ('length', 'max_tokens'):
                statuses.append('incomplete'); details.append({'pointer': ptr+'/finish_reason', 'value': value['finish_reason']})
    status = 'FAIL' if 'incomplete' in statuses else 'PASS' if 'completed' in statuses else 'INCONCLUSIVE'
    return finding('provider_response_completion', status, report['run_id'],
                   'PROVIDER_MARKED_INCOMPLETE' if status == 'FAIL' else 'PROVIDER_MARKED_COMPLETED' if status == 'PASS' else 'COMPLETION_METADATA_OR_ORIGIN_UNRESOLVED',
                   'bound report response carries completed provider status',
                   {'report_id': report['id'], 'metadata': details, 'origin_status': report.get('origin_status')}, refs=refs,
                   limits=['Completed provider status does not certify complete analysis; unresolved render origins stay unresolved.'])


def source_findings(ctx, run_id):
    findings = []; sources = ctx.rows_for('sources', run_id)
    parsed = []
    for source in sources:
        status = source.get('source_status', 'UNKNOWN')
        findings.append(finding('recorded_source_availability', 'PASS' if status == 'AVAILABLE' else 'INCONCLUSIVE', run_id,
                                'AVAILABLE_RETURN_OBSERVED' if status == 'AVAILABLE' else 'SOURCE_RESULT_NOT_AVAILABLE',
                                'source returns available data', {'status': status, 'tool': source.get('tool'),
                                'source_version': source.get('source_version'), 'retrieved_at': source.get('retrieved_at')},
                                refs=[ctx.ref(source)], limits=['Retrieval status is not source correctness or failed invocation.']))
        if status != 'AVAILABLE':
            continue
        content = source.get('content', '')
        rows = ck.bars(content)
        if source.get('tool') in ('get_stock_data', 'get_verified_market_snapshot') and not rows:
            findings.append(finding('source_ohlc_bounds', 'INCONCLUSIVE', run_id, 'OHLC_LAYOUT_UNRECOGNIZED',
                                    'dated, numeric OHLC row', {'source_id': source['id']}, refs=[ctx.ref(source)]))
        for bar in rows:
            values = {key: slot['value'] for key, slot in bar['fields'].items()}
            result, observed = ck.ohlc(values)
            findings.append(finding('source_ohlc_bounds', result, run_id,
                                    'OHLC_BOUNDS_VIOLATION' if result == 'FAIL' else 'OHLC_BOUNDS_HOLD' if result == 'PASS' else 'OHLC_VALUES_UNRESOLVED',
                                    'Low <= Open, Close <= High and Low <= High', dict(observed, date=bar['date'], layout=bar['kind']),
                                    refs=[ctx.ref(source)], spans=[ctx.ref(source, bar['start'], bar['end'])],
                                    limits=['Checks saved provider-row mathematics; does not establish true market prices or candle finality.']))
            parsed.append((source, bar))
    # Compare only unique dated rows from each distinct version/tool and same explicit instrument.
    for i, (left, a) in enumerate(parsed):
        for right, b in parsed[i+1:]:
            if left['id'] == right['id'] or a['date'] != b['date'] or {a['kind'], b['kind']} != {'csv_ohlc', 'snapshot_ohlc'}:
                continue
            symbol_a = (left.get('args') or {}).get('symbol') or (left.get('args') or {}).get('ticker')
            symbol_b = (right.get('args') or {}).get('symbol') or (right.get('args') or {}).get('ticker')
            if not symbol_a or not symbol_b or symbol_a != symbol_b:
                continue
            differences = {}; unparsed = []
            for field in ck.FIELDS:
                try:
                    if ck.decimal(a['fields'][field]['value']) != ck.decimal(b['fields'][field]['value']):
                        differences[field] = {'left': a['fields'][field]['value'], 'right': b['fields'][field]['value']}
                except ValueError:
                    unparsed.append(field)
            result = 'FAIL' if differences else 'INCONCLUSIVE' if unparsed else 'PASS'
            findings.append(finding('within_run_csv_snapshot_agreement', result, run_id,
                                    'RECORDED_VERSIONS_DIFFER' if differences else 'UNPARSEABLE_COMPARISON' if unparsed else 'RECORDED_VALUES_AGREE',
                                    'same-run explicitly matched symbol/date OHLC values agree',
                                    {'symbol': symbol_a, 'date': a['date'], 'differences': differences, 'unparsed_fields': unparsed,
                                     'left_retrieved_at': left.get('retrieved_at'), 'right_retrieved_at': right.get('retrieved_at')},
                                    refs=[ctx.ref(left), ctx.ref(right)],
                                    spans=[ctx.ref(left, a['start'], a['end']), ctx.ref(right, b['start'], b['end'])],
                                    limits=['FAIL means observed version disagreement, not a verdict choosing a true price; asynchronous values may differ.']))
    return findings


def url_findings(ctx, run_id):
    findings = []; occurrences = defaultdict(list)
    for source in ctx.rows_for('sources', run_id):
        if source.get('source_status') != 'AVAILABLE':
            continue
        for url in ck.urls(source.get('content', '')):
            occurrences[url['value']].append((source, url))
    repeated = {url: rows for url, rows in occurrences.items() if len(rows) > 1}
    refs = [ctx.ref(source, url['start'], url['end']) for rows in repeated.values() for source, url in rows]
    findings.append(finding('exact_url_duplicate_lineage', 'PASS', run_id, 'EXACT_URL_INVENTORY_ONLY',
                            'count URL occurrences separately from exact per-run identities',
                            {'occurrences': sum(len(v) for v in occurrences.values()), 'distinct_urls': len(occurrences),
                             'repeated_occurrences': sum(len(v)-1 for v in occurrences.values()),
                             'repeated_urls': sorted(repeated)}, spans=refs,
                            limits=['Inventory PASS does not imply report deduplication, independent corroboration or publisher identity.']))
    for report in ctx.rows_for('reports', run_id):
        text, call = ctx.report_call(report)
        if not text:
            continue
        visible = ctx.exposed_sources(call) if call else []
        for url in ck.markdown_citations(text.get('text', '')):
            matches = []
            for source, exposure in visible:
                if source.get('source_status') != 'AVAILABLE':
                    continue
                for item in ck.urls(source.get('content', '')):
                    if item['value'] == url['value']:
                        matches.append((source, exposure, item))
            findings.append(finding('citation_preinput_provenance', 'PASS' if matches else 'INCONCLUSIVE', run_id,
                                    'EXACT_CITATION_IN_PRIOR_INPUT_SOURCE' if matches else 'CITATION_SOURCE_OR_ORIGIN_UNRESOLVED',
                                    'exact report Markdown URL occurs in available same-run source exposed before this call',
                                    {'url': url['value'], 'report_id': report['id'], 'matching_source_ids': sorted({s['id'] for s, _, _ in matches})},
                                    refs=[ctx.ref(report)]+[ctx.ref(e) for _, e, _ in matches],
                                    spans=[ctx.ref(text, url['start'], url['end'])]+[ctx.ref(s, u['start'], u['end']) for s, _, u in matches],
                                    limits=['Checks URL provenance only, not article bodies, actuality, relevance or claim entailment.']))
    return findings


def acknowledgement_findings(ctx, report):
    text, call = ctx.report_call(report)
    if not text or not call:
        return []
    body = text.get('text', '')
    # A lexical acknowledgement, not full contradiction/negative scope understanding.
    families = [
        ('fred', r'\bFRED\b|macro(?:economic)?', r'\bFRED\b|macro(?:economic)?'),
        ('eth_news', r'get_news', r'ETH.{0,25}news|news.{0,25}ETH|asset.specific|ticker.specific|crypto.specific|coin.specific'),
        ('snapshot', r'get_verified_market_snapshot', r'snapshot'),
    ]
    missing = [(s, e) for s, e in ctx.exposed_sources(call) if s.get('source_status') != 'AVAILABLE']
    for family, source_pattern, report_pattern in families:
        relevant = [(s, e) for s, e in missing if re.search(source_pattern,
                    ' '.join(str(s.get(k, '')) for k in ('tool', 'provider', 'content')), re.I)]
        if not relevant:
            continue
        anchors = []
        for match in re.finditer(report_pattern, body, re.I):
            start = max(0, body.rfind('\n', 0, match.start())+1)
            next_line = body.find('\n', match.end()); end = len(body) if next_line < 0 else next_line
            if re.search(r'missing|unavailable|not (?:available|retrieved|returned|verified)|no\b|lack|cannot|could not|did not|without|MISSING_CREDENTIAL|SOURCE_UNAVAILABLE|NO_DATA|no valid|not run', body[start:end], re.I):
                anchors.append(ctx.ref(text, start, end))
        yield finding('missing_source_acknowledgement', 'PASS' if anchors else 'INCONCLUSIVE', report['run_id'],
                      'LEXICAL_MISSING_SOURCE_ACKNOWLEDGEMENT' if anchors else 'ACKNOWLEDGEMENT_NOT_ESTABLISHED_BY_GRAMMAR',
                      'report explicitly acknowledges exposed unavailable source family',
                      {'family': family, 'statuses': sorted({s.get('source_status', 'UNKNOWN') for s, _ in relevant}),
                       'report_id': report['id']}, refs=[ctx.ref(report)]+[ctx.ref(s) for s, _ in relevant]+[ctx.ref(e) for _, e in relevant],
                      spans=anchors, limits=['Lexical recognition preserves full lines; absence is inconclusive rather than an invented failed obligation.'])


def conflict_acknowledgements(ctx, report, conflicts):
    """Lexical discrepancy disclosure only; no automatic truth/error attribution."""
    text, call = ctx.report_call(report)
    if not text or not call:
        return []
    visible = {s['id']: e for s, e in ctx.exposed_sources(call)}
    result = []
    for conflict in conflicts:
        ids = {ref['id'] for ref in conflict['source_refs']}
        if not ids <= visible.keys() or conflict['status'] != 'FAIL':
            continue
        anchors = []
        for match in re.finditer(r'mismatch|discrepanc\w*|differ\w*|conflict\w*|inconsisten\w*', text['text'], re.I):
            a = text['text'].rfind('\n', 0, match.start())+1
            b = text['text'].find('\n', match.end())
            b = len(text['text']) if b < 0 else b
            if re.search(r'snapshot|CSV|stock.data|close|OHLC|price', text['text'][a:b], re.I):
                anchors.append(ctx.ref(text, a, b))
        result.append(finding('source_conflict_acknowledgement', 'PASS' if anchors else 'INCONCLUSIVE', report['run_id'],
                              'LEXICAL_SOURCE_DISCREPANCY_DISCLOSURE' if anchors else 'DISCREPANCY_DISCLOSURE_NOT_ESTABLISHED_BY_GRAMMAR',
                              'market report discloses a source-value discrepancy after exposure to both versions',
                              {'report_id': report['id'], 'conflict_finding_id': conflict['finding_id'],
                               'semantic_resolution': 'INCONCLUSIVE'},
                              refs=[ctx.ref(report)]+conflict['source_refs']+[ctx.ref(visible[i]) for i in sorted(ids)],
                              spans=anchors,
                              limits=['Lexical acknowledgement does not certify the correct price, complete comparison, or accepted version authority.']))
    return result


def clock_context(ctx, run_id):
    runs = ctx.rows_for('runs', run_id)
    context = runs[0].get('context', {}) if len(runs) == 1 else {}
    sources = ctx.rows_for('sources', run_id)
    dates = sorted({bar['date'] for s in sources if s.get('source_status') == 'AVAILABLE'
                    for bar in ck.bars(s.get('content', ''))})
    selected = {key: context.get(key) for key in ('trade_date', 'context_at', 'context_timezone',
                'local_context_at', 'local_timezone', 'utc_date', 'local_date', 'date_basis')}
    captured = selected['trade_date'] is not None and selected['context_at'] is not None
    return finding('recorded_date_clock_context', 'PASS' if captured else 'INCONCLUSIVE', run_id,
                   'CLOCKS_RECORDED_WITHOUT_FRESHNESS_INFERENCE' if captured else 'CLOCK_METADATA_INCOMPLETE',
                   'retain analysis/retrieval clocks and dated rows without inventing finality or TTL',
                   {'context': selected, 'parsed_source_row_dates': dates,
                    'sources_without_provider_time_fields': sum(not s.get('source_time_fields') for s in sources),
                    'freshness_TTL': 'INCONCLUSIVE', 'candle_finality': 'INCONCLUSIVE'},
                   refs=[ctx.ref(row) for row in runs],
                   limits=['Different host-local/UTC dates are observations, not an automatic stale-data or incorrect-date verdict.'])


def numerical_findings(ctx, run_id):
    findings = []; selection = Counter()
    candidates = sorted(ctx.rows_for('candidates', run_id), key=lambda c:(str(c.get('text_id')), c.get('end', 0)-c.get('start', 0), c.get('start', 0), c['id']))
    # Unique text/span candidates prevent parallel annotations from multiplying checks.
    seen = set(); selected_scalars = set(); selected_equations = set(); selected_envelopes = set()
    for candidate in candidates:
        text = ctx.get(candidate.get('text_id'), 'texts')
        if not text or not isinstance(candidate.get('start'), int) or not isinstance(candidate.get('end'), int):
            continue
        a, b = candidate['start'], candidate['end']
        if not 0 <= a <= b <= len(text.get('text', '')) or candidate.get('quote') != text.get('text', '')[a:b]:
            raise ValueError('candidate canonical span binding invalid')
        key = (text['id'], a, b)
        if key in seen:
            continue
        seen.add(key)
        body = text.get('text', '')[a:b]
        selection['candidate_envelopes'] += 1
        if re.search(r'\d', body):
            selection['candidate_envelopes_with_digits'] += 1
        call = ctx.get(text.get('call_id'), 'calls')
        visible = ctx.exposed_sources(call) if call else []
        for slot in ck.scalar_slots(body):
            identity = (text['id'], a+slot['start'], a+slot['end'], slot['field'])
            # A truncated candidate must not turn 33.07 into an asserted 33.
            if re.match(r'(?:\d|[.,]\d)', text['text'][a+slot['end']:]):
                continue
            if identity in selected_scalars:
                continue
            selected_scalars.add(identity); selected_envelopes.add(key)
            selection['selected_explicit_scalar_slots'] += 1
            matches = []; available = []
            for source, exposure in visible:
                if source.get('source_status') != 'AVAILABLE' or source.get('tool') != 'get_verified_market_snapshot':
                    continue
                for scalar in ctx.source_scalars(source):
                    if scalar['field'] != slot['field']:
                        continue
                    available.append((source, exposure, scalar))
                    try:
                        equal, detail = ck.rounded_equal(slot['value'], scalar['value'])
                    except ValueError:
                        continue
                    if equal:
                        matches.append((source, exposure, scalar, detail))
            # PASS only scoped label+rounded number agreement, never factual support.
            result = 'PASS' if matches else 'INCONCLUSIVE'
            reason = 'EXPLICIT_LABEL_NUMBER_ROUNDING_MATCH' if matches else 'SCALAR_ALIGNMENT_NOT_ESTABLISHED'
            selection['scalar_matches' if matches else 'scalar_unresolved'] += 1
            findings.append(finding('selected_scalar_source_consistency', result, run_id, reason,
                                    'explicit same-field number equals an available pre-input snapshot value at displayed precision',
                                    {'field': slot['field'], 'asserted': slot['value'],
                                     'matched_values': [dict(d, source_id=s['id'], source_date=v['date']) for s, _, v, d in matches],
                                     'candidate_source_values': [v['value'] for _, _, v in available],
                                     'semantic_alignment': 'INCONCLUSIVE'},
                                    refs=[ctx.ref(s) for s, _, _, _ in matches]+[ctx.ref(e) for _, e, _, _ in matches],
                                    candidates=[ctx.ref(candidate)],
                                    spans=[ctx.ref(text, a+slot['start'], a+slot['end'])]+[ctx.ref(s, v['start'], v['end']) for s, _, v, _ in matches],
                                    scope='restricted_label_and_rounded_number_agreement_only',
                                    limits=['No date/entity/negation/conditional role is inferred from a lexical number match. This does not verify assertion truth or full numeric coverage.']))
        for eq in ck.arithmetic(body):
            identity = (text['id'], a+eq['start'], a+eq['end'])
            if re.match(r'(?:\d|[.,]\d)', text['text'][a+eq['end']:]):
                continue
            if identity in selected_equations:
                continue
            selected_equations.add(identity); selected_envelopes.add(key)
            selection['selected_explicit_subtraction_equations'] += 1
            passage = ctx.get(candidate.get('passage_id'), 'passages')
            left, right = (passage['start'], passage['end']) if passage and passage.get('text_id') == text['id'] else (a, b)
            context = text['text'][left:right]
            conditions = bool(re.search(r'\bif\b|assuming|provided|conditional|same|identical|settlement|resolution|rules', context, re.I))
            findings.append(finding('selected_subtraction_arithmetic', eq['status'], run_id,
                                    'SUBTRACTION_EQUALITY_HOLDS' if eq['status'] == 'PASS' else 'SUBTRACTION_EQUALITY_FAILS',
                                    'displayed a minus b equals c', dict(eq, condition_wording_observed=conditions,
                                    settlement_alignment='INCONCLUSIVE', quote_synchronization='INCONCLUSIVE',
                                    unit_interpretation='INCONCLUSIVE'),
                                    refs=[ctx.ref(passage)] if passage else [],
                                    candidates=[ctx.ref(candidate)], spans=[ctx.ref(text, left, right), ctx.ref(text, a+eq['start'], a+eq['end'])],
                                    scope='displayed_numeric_coefficients_only',
                                    limits=['Only displayed arithmetic checked; conditions in the full candidate remain attached. No probability distribution or settlement compatibility is certified.']))
    selection['selected_candidate_envelopes'] = len(selected_envelopes)
    selection['unselected_digit_candidate_envelopes'] = selection['candidate_envelopes_with_digits'] - len(selected_envelopes)
    selection['canonical_numeric_atoms'] = sum(atom.get('kind') == 'numeric' for atom in ctx.rows_for('atoms', run_id))
    findings.append(finding('numerical_selection_coverage', 'INCONCLUSIVE', run_id, 'RESTRICTED_GRAMMAR_SELECTION_NOT_SEMANTIC_RECALL',
                            'explicit denominator and selected/unassessed scope', dict(selection, total_canonical_candidates=len(candidates)),
                            coverage=dict(selection), limits=['Unselected percentages, thresholds, sizing, forecasts and qualitative/causal claims remain unassessed. No random sample or semantic recall denominator.']))
    return findings


def assess_rows(rows):
    """Pure assessment; caller supplies a validated canonical ledger, never raw files."""
    ctx = Context(rows); findings = []
    run_ids = sorted({r['run_id'] for r in rows if r.get('run_id') is not None})
    for run_id in run_ids:
        source_results = source_findings(ctx, run_id)
        findings.extend(source_results)
        findings.extend(url_findings(ctx, run_id))
        findings.extend(numerical_findings(ctx, run_id))
        findings.append(clock_context(ctx, run_id))
        reports = ctx.rows_for('reports', run_id)
        for report in reports:
            if report.get('field') == 'market_report':
                findings.extend(protocol_findings(ctx, report))
                findings.extend(conflict_acknowledgements(ctx, report, [f for f in source_results if f['rule_id'] == 'within_run_csv_snapshot_agreement']))
            findings.append(report_completeness(ctx, report))
            findings.extend(acknowledgement_findings(ctx, report))
        findings.append(finding('unresolved_semantic_and_time_limits', 'INCONCLUSIVE', run_id,
                                'NO_ACCEPTED_POLICY_OR_COMPLETE_DEPENDENCY_BINDING',
                                'accepted TTL/finality/version authority, full dependency model and suitability criteria',
                                {'freshness_TTL': 'INCONCLUSIVE', 'candle_finality': 'INCONCLUSIVE',
                                 'version_authority': 'INCONCLUSIVE', 'full_semantic_dependency': 'INCONCLUSIVE',
                                 'decision_suitability': 'INCONCLUSIVE', 'feedback_or_live_repair': False,
                                 'unresolved_rows': len(ctx.rows_for('unresolved', run_id)),
                                 'report_count': len(reports), 'canonical_candidate_count': len(ctx.rows_for('candidates', run_id))},
                                refs=[ctx.ref(r) for r in ctx.rows_for('runs', run_id)],
                                limits=['No synthetic 60-second TTL is transferred to these live provider results.']))
    # Identical findings can arise from duplicate lexical aliases; do not double count.
    return sorted({r['finding_id']: r for r in findings}.values(), key=lambda r:r['finding_id'])


def _all_findings(rows, ledger_sha):
    findings = assess_rows(rows)
    findings.append(finding('canonical_ledger_integrity', 'PASS', None, 'CANONICAL_BINDINGS_VALIDATED',
                            'ledger validator accepts canonical index/source/span bindings',
                            {'ledger_sha256': ledger_sha}, scope='canonical_ledger_validation_only',
                            limits=['Original-session artifact revalidation belongs to the parent; canonical integrity is not semantic truth.']))
    return sorted(findings, key=lambda r:r['finding_id'])


def _implementation_binding():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), Path(ck.__file__), Path(__file__).with_name('RULES_POLICY.md')]}


def _write_index(path, findings):
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE findings(finding_id TEXT PRIMARY KEY,rule_id TEXT NOT NULL,status TEXT NOT NULL,run_id TEXT,row_json TEXT NOT NULL)')
        db.executemany('INSERT INTO findings VALUES(?,?,?,?,?)', [(r['finding_id'],r['rule_id'],r['status'],r['run_id'],canonical(r)) for r in findings])
        db.execute('CREATE INDEX findings_by_rule_status ON findings(rule_id,status)')
        db.commit()


def _summary(findings, ledger_sha256):
    by_rule = defaultdict(Counter)
    for row in findings:
        by_rule[row['rule_id']][row['status']] += 1
    return {'method_version': VERSION, 'policy_version': POLICY_VERSION,
            'ledger_sha256': ledger_sha256, 'finding_count': len(findings),
            'status_counts': dict(Counter(r['status'] for r in findings)),
            'by_rule': {k: dict(v) for k,v in sorted(by_rule.items())},
            'clearance': None, 'feedback_or_repair': False, 'limitations': LIMITS}


def _report(summary, findings):
    lines = ['# Live ledger verification findings', '',
             'These are scoped deterministic findings over the canonical live ledger. No global clearance or model ranking is assigned.', '',
             f"Canonical ledger SHA256: `{summary['ledger_sha256']}`. Findings: {summary['finding_count']}.", '',
             '| Rule | PASS | FAIL | INCONCLUSIVE | ERROR |', '|---|---:|---:|---:|---:|']
    for rule, counts in summary['by_rule'].items():
        lines.append('| '+rule+' | '+' | '.join(str(counts.get(k, 0)) for k in ('PASS','FAIL','INCONCLUSIVE','ERROR'))+' |')
    lines += ['', 'FAIL can mean an omitted scoped invocation, a mathematical violation, a recorded version disagreement or an incomplete provider response. It is not a global truth or model-quality verdict.', '',
              'Numerical checks select explicit label/value slots and displayed subtraction equations from canonical candidates. The coverage finding gives denominators per run; full semantic recall is unknown. Matching values do not establish date/entity alignment, suitability or factual entailment.', '',
              'All findings, including PASS and INCONCLUSIVE, have deterministic IDs and queryable expected/observed fields and canonical row/span references in findings.jsonl and findings.sqlite.', '',
              '## Findings needing attention', '']
    for row in findings:
        if row['status'] == 'FAIL':
            lines += [f"- `{row['finding_id']}` — {row['run_id']} / {row['rule_id']}: {row['reason_code']}.",
                      '  Observed: '+canonical(row['observed'])]
    lines += ['', '## Limits', '']+[f'- {limit}' for limit in LIMITS]
    return '\n'.join(lines)+'\n'


def assess_ledger(ledger_dir: Path, dest: Path):
    """Validate canonical inputs, then create a new assessment directory only."""
    ledger_dir = Path(ledger_dir).resolve(); dest = Path(dest).resolve()
    if dest.exists():
        raise FileExistsError('assessment destination already exists')
    if dest == ledger_dir or ledger_dir in dest.parents or dest in ledger_dir.parents:
        raise ValueError('assessment destination must be separate from canonical ledger')
    from .ledger import load_ledger, validate_ledger
    validation = validate_ledger(ledger_dir)
    rows = load_ledger(ledger_dir)
    ledger_path = ledger_dir/'ledger.jsonl'
    ledger_sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    findings = _all_findings(rows, ledger_sha)
    summary = _summary(findings, ledger_sha)
    raw = ''.join(canonical(r)+'\n' for r in findings).encode('utf-8')
    summary['findings_sha256'] = hashlib.sha256(raw).hexdigest()
    summary['implementation_binding'] = _implementation_binding()
    dest.mkdir(parents=True, exist_ok=False)
    (dest/'findings.jsonl').write_bytes(raw)
    _write_index(dest/'findings.sqlite', findings)
    (dest/'summary.json').write_text(canonical(summary)+'\n', encoding='utf-8')
    (dest/'input-validation.json').write_text(canonical(validation)+'\n', encoding='utf-8')
    (dest/'REPORT.md').write_text(_report(summary, findings), encoding='utf-8')
    validate_assessment(dest, ledger_dir)
    return summary


def validate_assessment(dest: Path, ledger_dir: Path | None = None):
    dest = Path(dest)
    raw = (dest/'findings.jsonl').read_bytes()
    findings = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
    summary = json.loads((dest/'summary.json').read_text(encoding='utf-8'))
    if summary.get('implementation_binding') != _implementation_binding():
        raise ValueError('assessment implementation binding mismatch')
    if hashlib.sha256(raw).hexdigest() != summary['findings_sha256']:
        raise ValueError('finding canonical hash mismatch')
    ids = [r['finding_id'] for r in findings]
    if ids != sorted(set(ids)) or raw != ''.join(canonical(r)+'\n' for r in findings).encode('utf-8'):
        raise ValueError('finding canonical order/identity invalid')
    for row in findings:
        body = dict(row); identity = body.pop('finding_id')
        if identity != 'live-finding:'+digest(body) or row['status'] not in STATUSES:
            raise ValueError('finding identity or status invalid')
    with closing(sqlite3.connect((dest/'findings.sqlite').resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('finding SQLite integrity error')
        indexed = [json.loads(r[0]) for r in db.execute('SELECT row_json FROM findings ORDER BY finding_id')]
        scalars = db.execute('SELECT finding_id,rule_id,status,run_id FROM findings ORDER BY finding_id').fetchall()
    if indexed != findings or scalars != [(r['finding_id'],r['rule_id'],r['status'],r['run_id']) for r in findings]:
        raise ValueError('finding SQLite logical parity mismatch')
    expected = _summary(findings, summary['ledger_sha256'])
    if any(summary.get(k) != value for k,value in expected.items()):
        raise ValueError('finding summary mismatch')
    if (dest/'REPORT.md').read_text(encoding='utf-8') != _report(summary, findings):
        raise ValueError('finding human report mismatch')
    if ledger_dir is not None:
        from .ledger import load_ledger, validate_ledger
        ledger_dir = Path(ledger_dir)
        validate_ledger(ledger_dir)
        if hashlib.sha256((ledger_dir/'ledger.jsonl').read_bytes()).hexdigest() != summary['ledger_sha256']:
            raise ValueError('assessment bound to another ledger')
        rows = load_ledger(ledger_dir)
        ctx = Context(rows)
        if _all_findings(rows, summary['ledger_sha256']) != findings:
            raise ValueError('finding deterministic assessment replay mismatch')
        for finding_row in findings:
            for ref in finding_row['source_refs']+finding_row['candidate_refs']+finding_row['span_refs']:
                source = ctx.get(ref.get('id'))
                if source is None or source['table'] != ref.get('table') or source['run_id'] != ref.get('run_id'):
                    raise ValueError('finding reference unresolved')
                if 'start' in ref:
                    if ctx.ref(source, ref['start'], ref['end']) != ref:
                        raise ValueError('finding span reference mismatch')
                elif ctx.ref(source) != ref:
                    raise ValueError('finding row reference mismatch')
    return {'status':'PASS', 'findings':len(findings), 'jsonl_sqlite_logical_parity':True,
            'canonical_sha256':summary['findings_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--dest', type=Path, required=True)
    args = parser.parse_args()
    print(canonical(assess_ledger(args.ledger, args.dest)))


if __name__ == '__main__':
    main()
