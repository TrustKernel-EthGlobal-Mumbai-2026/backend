"""Conservative accounting, distinct from a provider invoice."""
def upper_charge(model, usage):
    # Charge every input token at the documented highest cache-write price,
    # even uncached/cache-read tokens. Output includes nonvisible tokens.
    inputs, outputs = usage.get('input_tokens'), usage.get('output_tokens')
    if not isinstance(inputs, int) or not isinstance(outputs, int) or inputs < 0 or outputs < 0:
        raise ValueError('Invalid or missing provider token counts')
    if inputs > 60000 or outputs > 2048:
        raise ValueError('Provider usage exceeds reserved request envelope')
    rates = (5, 10) if model.endswith('sol') else (2.5, 5)
    return (inputs*rates[0] + outputs*rates[1])/1e6


def message_usage(payload):
    found = {}
    def walk(value):
        if isinstance(value, dict):
            response_id = value.get('response_metadata', {}).get('id') or value.get('id')
            if response_id and value.get('usage_metadata'):
                found[response_id] = value['usage_metadata']
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(payload)
    return found
