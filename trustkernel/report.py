"""Descriptive trace summary; no reasoning-quality or profitability score."""
import json
from collections import Counter
from pathlib import Path


def summarize(directory):
    directory = Path(directory)
    events = [json.loads(line) for line in (directory / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
    counts = Counter(e['kind'] for e in events)
    usage_by_id = {}
    def find_usage(value):
        if isinstance(value, dict):
            identity = value.get('response_metadata', {}).get('id') or value.get('id')
            if identity and value.get('usage_metadata'):
                usage_by_id[identity] = value['usage_metadata']
            for item in value.values():
                find_usage(item)
        elif isinstance(value, list):
            for item in value:
                find_usage(item)
    for event in events:
        find_usage(event['payload'])
    inputs, outputs, usage_calls = 0, 0, 0
    for e in events:
        if e['kind'] != 'llm.end':
            continue
        response = e['payload']['response']
        usage = None
        for batch in response.get('generations', []):
            for generation in batch:
                message = generation.get('message', {})
                identity = message.get('response_metadata', {}).get('id') or message.get('id')
                usage = message.get('usage_metadata') or usage_by_id.get(identity) or usage
        if usage:
            inputs += usage.get('input_tokens', 0)
            outputs += usage.get('output_tokens', 0)
            usage_calls += 1
    model = events[0]['context']['model']
    paid = events[0]['context']['mode'] == 'paid'
    rates = (2, 10) if model.endswith('sol') else (1, 5)
    report = dict(event_counts=dict(counts), input_tokens=inputs, output_tokens=outputs,
                  usage_calls=usage_calls, inference=events[0]['context']['inference'],
                  estimated_standard_cost_usd=(inputs*rates[0]+outputs*rates[1])/1e6 if usage_calls else None,
                  cost_note='Estimate only, includes reported total output tokens; budget reservation remains conservative. No inference costs in offline mode.',
                  actual_api_access_verified=paid and counts['run.end'] > 0,
                  errors=counts['run.error']+counts['llm.error']+counts['tool.error'],
                  quality_score=None)
    (directory / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (directory / 'summary.md').write_text(
        f"# {model} trace summary\n\nMode: {report['inference']}. Events: {len(events)}. "
        f"LLM calls completed: {counts['llm.end']}. Tool calls completed: {counts['tool.end']}. "
        f"Evidence retrievals: {counts['evidence.retrieved']}.\n\n"
        f"Reported input/output tokens: {inputs}/{outputs}; calls reporting usage: {usage_calls}. "
        f"Estimated standard API cost: {report['estimated_standard_cost_usd']}.\n\n"
        'No quality score is assigned. Scripted smoke outputs do not compare model capabilities. '
        'Full observable payloads are in trace.jsonl; use the viewer or SQLite for inspection.\n', encoding='utf-8')
    return report
