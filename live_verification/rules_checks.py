"""Pure, bounded checks on persisted strings; no corpus, providers or models.

These functions establish mathematical/lexical relations only. Callers must
bind their offsets to canonical ledger rows and pre-assertion source exposure.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import csv
import io
import re

NUMBER = r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
FIELDS = ('Open', 'High', 'Low', 'Close')
URL = re.compile(r'https?://[^\s<>\[\]"`]+')


def decimal(value):
    if not isinstance(value, str) or not re.fullmatch(NUMBER, value.strip()):
        raise ValueError('finite decimal string required')
    try:
        out = Decimal(value.replace(',', '').strip())
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not out.is_finite():
        raise ValueError('nonfinite decimal')
    return out


def ohlc(values):
    """Missing/unparseable values are unknown, never a mathematical failure."""
    try:
        v = {k: decimal(values[k]) for k in FIELDS}
    except (KeyError, TypeError, ValueError):
        return 'INCONCLUSIVE', {'reason': 'missing_or_unparseable_ohlc'}
    violations = [f'Low <= {k} <= High' for k in ('Open', 'Close')
                  if not v['Low'] <= v[k] <= v['High']]
    if v['Low'] > v['High']:
        violations.append('Low <= High')
    return ('FAIL' if violations else 'PASS'), {'values': values, 'violations': violations}


def rounded_equal(asserted, source):
    """Decimal half-up at the asserted precision; no relative tolerance."""
    a, s = decimal(asserted), decimal(source)
    precision = max(0, -a.as_tuple().exponent)
    unit = Decimal(1).scaleb(-precision)
    try:
        rounded = s.quantize(unit, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError('precision outside decimal context') from exc
    return a == rounded, {'asserted': str(a), 'source': str(s),
                         'rounded_source': str(rounded), 'decimal_places': precision,
                         'rounding': 'ROUND_HALF_UP'}


def urls(text):
    """Exact URL identity only; no normalization, fetch, syndication inference."""
    result = []
    for m in URL.finditer(text):
        # Native markdown/table delimiters are syntax, not URL characters.
        value = m.group().rstrip('.,;!|')
        while value.endswith(')') and value.count(')') > value.count('('):
            value = value[:-1]
        if value:
            result.append({'value': value, 'start': m.start(), 'end': m.start()+len(value)})
    return result


def markdown_citations(text):
    out = []
    for m in re.finditer(r'\[[^\]\n]+\]\((https?://[^\s)]+)\)', text):
        a, b = m.span(1)
        out.append({'value': m[1], 'start': a, 'end': b})
    return out


def bars(text):
    """Recognize CSV OHLC headers or the native markdown snapshot layout.

    Returns source-relative code-point spans. No requested date is substituted
    for a missing row date, and recent-close tables are not full OHLC rows.
    """
    lines = text.splitlines(keepends=True)
    offsets = []; pos = 0
    for line in lines:
        offsets.append(pos); pos += len(line)
    result = []
    for i, line in enumerate(lines):
        try:
            header = next(csv.reader([line]))
        except csv.Error:
            continue
        if not {'Date', *FIELDS}.issubset(header):
            continue
        for j in range(i+1, len(lines)):
            try:
                values = next(csv.reader([lines[j]]))
            except csv.Error:
                break
            if len(values) != len(header):
                break
            row = dict(zip(header, values))
            date = row.get('Date', '')
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[ T].*)?', date):
                break
            fields = {}; cursor = 0
            for key, val in zip(header, values):
                # Quoted commas are handled by csv; offsets locate exact text.
                a = lines[j].find(val, cursor)
                if a < 0:
                    fields = {}; break
                cursor = a+len(val)
                if key in (*FIELDS, 'Volume'):
                    fields[key] = {'value': val, 'start': offsets[j]+a,
                                   'end': offsets[j]+a+len(val)}
            if all(k in fields for k in FIELDS):
                result.append({'date': date[:10], 'kind': 'csv_ohlc', 'fields': fields,
                               'start': offsets[j], 'end': offsets[j]+len(lines[j].rstrip('\r\n'))})
        break
    date = re.search(r'Latest trading row used:\s*(\d{4}-\d{2}-\d{2})', text)
    section = re.search(r'### Latest verified OHLCV row\s*\n(?P<body>.*?)(?=\n###|\Z)', text, re.S)
    if date and section:
        fields = {}
        for m in re.finditer(r'^\|\s*(Open|High|Low|Close|Volume)\s*\|\s*([^|\r\n]+?)\s*\|', section['body'], re.M):
            a, b = m.span(2)
            fields[m[1]] = {'value': m[2], 'start': section.start('body')+a,
                            'end': section.start('body')+b}
        if all(k in fields for k in FIELDS):
            result.append({'date': date[1], 'kind': 'snapshot_ohlc', 'fields': fields,
                           'start': section.start(), 'end': section.end()})
    return result


def scalar_slots(text):
    """Restricted explicit label/value grammar, not general semantic parsing."""
    aliases = {'rsi': 'rsi', 'atr': 'atr', 'open': 'Open', 'high': 'High',
               'low': 'Low', 'close': 'Close', 'volume': 'Volume'}
    pattern = re.compile(r'\b(?P<field>open|high|low|close|volume|rsi|atr)\b'
                         r'(?:\*\*)?\s*(?:\([^\n)]{0,30}\))?\s*'
                         r'(?:(?:of|at|was|is)\s+|[:=|]\s*|\s*)'
                         r'(?:\*\*)?\$?\s*(?P<value>'+NUMBER+r')\b', re.I)
    out = []
    for m in pattern.finditer(text):
        out.append({'field': aliases[m['field'].lower()], 'value': m['value'],
                    'start': m.start('value'), 'end': m.end('value'),
                    'label_start': m.start('field'), 'label_end': m.end('field')})
    return out


def snapshot_scalars(text):
    out = []
    for bar in bars(text):
        for field, slot in bar['fields'].items():
            out.append(dict(slot, field=field, date=bar['date'], origin=bar['kind']))
    section = re.search(r'### Verified technical indicators[^\n]*\n(?P<body>.*?)(?=\n###|\Z)', text, re.S)
    if section:
        for m in re.finditer(r'^\|\s*(rsi|atr)\s*\|\s*('+NUMBER+r')\s*\|', section['body'], re.M|re.I):
            a, b = m.span(2)
            date = re.search(r'Latest trading row used:\s*(\d{4}-\d{2}-\d{2})', text)
            out.append({'field': m[1].lower(), 'value': m[2], 'start': section.start('body')+a,
                        'end': section.start('body')+b, 'date': date[1] if date else None,
                        'origin': 'snapshot_indicator'})
    return out


def arithmetic(text):
    """Explicit a-b=c / c=a-b equations only; conditions stay attached by caller."""
    patterns = [
        (re.compile(r'(?P<a>'+NUMBER+r')\s*%?\s*[-−–]\s*(?P<b>'+NUMBER+r')\s*%?\s*=\s*(?P<c>'+NUMBER+r')\s*%?'), False),
        (re.compile(r'(?P<c>'+NUMBER+r')\s*%?\s*=\s*(?P<a>'+NUMBER+r')\s*%?\s*[-−–]\s*(?P<b>'+NUMBER+r')\s*%?'), True),
    ]
    found = []
    occupied = []
    for pattern, _ in patterns:
        for m in pattern.finditer(text):
            if any(m.start() < b and a < m.end() for a, b in occupied):
                continue
            occupied.append(m.span())
            a, b, c = (decimal(m[k]) for k in ('a', 'b', 'c'))
            found.append({'start': m.start(), 'end': m.end(), 'text': m.group(),
                          'a': str(a), 'b': str(b), 'c': str(c), 'computed': str(a-b),
                          'status': 'PASS' if a-b == c else 'FAIL'})
    return sorted(found, key=lambda r:r['start'])
