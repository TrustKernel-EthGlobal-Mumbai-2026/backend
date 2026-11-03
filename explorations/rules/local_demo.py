"""Small contract demonstration; no judge engine, network, API or gold labels.

Inputs are the frozen fixture and worker-authored abstract counterexamples.
Writes only explorations/rules/notes/demo-results.json. Assertions validate
the selected mechanisms under declared normalization, not their general quality.
"""
from decimal import Decimal, localcontext
from pathlib import Path
import csv
import hashlib
import io
import json

ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
SESSION = ROOT/'runs/20261030-010033-30min-597a75'


def main():
    fixture = json.loads((SESSION/'fixture.json').read_text(encoding='utf-8'))
    packet = json.loads((LANE/'notes/source-packet.json').read_text(encoding='utf-8'))
    rows = list(csv.DictReader(io.StringIO(fixture['tools']['get_stock_data']['content'].split('\n', 1)[1])))
    results = []

    def record(id_, observed, expected, basis, kind='mechanism assertion'):
        assert observed == expected, (id_, observed, expected)
        results.append(dict(id=id_, observed=observed, expected=expected,
                            basis=basis, kind=kind, result='PASS'))

    # Independently resolve the stored decoded source spans and byte hashes.
    for item in packet['references']:
        r = item['reference']
        path = ROOT/r['path']
        record(item['id']+'-hash', hashlib.sha256(path.read_bytes()).hexdigest(), r['sha256'], r['path'])
        text = json.loads(path.read_text(encoding='utf-8'))[r['pointer'][1:]]
        record(item['id']+'-span', text[r['start']:r['end']], r['quote'], r['path']+r['pointer'])
    r = packet['references'][0]['reference']
    text = json.loads((ROOT/r['path']).read_text(encoding='utf-8'))[r['pointer'][1:]]
    record('mutated-span', text[r['start']+1:r['end']] == r['quote'], False,
           'Counterexample: one-code-point offset mutation; no raw file changed')

    close = Decimal(rows[-1]['Close'])
    record('close-equality', close == Decimal('2540'), True, 'R01; E_PRICE date 2026-10-28')
    record('mutated-close', close == Decimal('2541'), False,
           'Counterexample based on R01; same tuple except value; same units/scope assumed')
    record('highs-increasing', all(Decimal(a['High']) < Decimal(b['High']) for a,b in zip(rows, rows[1:])), True, 'R02; E_PRICE')
    record('lows-increasing', all(Decimal(a['Low']) < Decimal(b['Low']) for a,b in zip(rows, rows[1:])), True, 'R02; E_PRICE')
    ranges = [str(Decimal(x['High'])-Decimal(x['Low'])) for x in rows]
    record('ranges', ranges, ['70','80','90'], 'R03; daily high minus low; no ATR formula')
    record('last-close-below-open', close < Decimal(rows[-1]['Open']), True, 'E_PRICE last row')
    record('last-close-below-previous', close < Decimal(rows[-2]['Close']), True, 'E_PRICE last two rows')
    with localcontext() as ctx:
        ctx.prec = 28
        change = str((close/Decimal(rows[-2]['Close'])-1)*100)
        sma3 = str(sum(Decimal(x['Close']) for x in rows)/3)
    results.append(dict(id='derived-unasserted', day_change_percent=change, sma3=sma3,
                        kind='local derived illustration, not a report claim or supplied indicator',
                        basis='E_PRICE; methods explicitly supplied in this script'))
    record('news-known-root-equality',
           fixture['tools']['get_news']['root_source_id'] == fixture['tools']['get_global_news']['root_source_id'],
           True, 'R06/R07; declared synthetic lineage only')
    calls = {(c['run_id'],c['seq']): c for c in packet['calls']}
    def exposure_at(rid, seq):
        call = calls[rid,seq]
        return {k: call['full_content_exposures'][k]+call['decoded_envelope_exposures'][k]
                for k in call['full_content_exposures']}
    market = exposure_at('terra-2f66dbe7f15d',73)
    news = exposure_at('terra-2f66dbe7f15d',139)
    record('literal-search-misses-escaped-csv',
           bool(calls['terra-2f66dbe7f15d',73]['full_content_exposures']['E_PRICE']), False,
           'E_PRICE newline characters are encoded inside a JSON envelope in the input')
    record('market-csv-and-snapshot-visible', bool(market['E_PRICE']) and bool(market['E_SNAPSHOT']), True,
           'R01/R05; exact fixture content after explicit envelope decoding in recorded input 73')
    record('news-no-direct-price-content', bool(news['E_PRICE']) or bool(news['E_SNAPSHOT']), False,
           'R08; exact full-content method only; no assertion of complete semantic absence')
    sol = exposure_at('sol-0530a9827c2c',67)
    record('sol-final-market-input-csv-visible', bool(sol['E_PRICE']), True, 'R02/R03; input 67')
    record('sol-final-market-input-no-snapshot-match', bool(sol['E_SNAPSHOT']), False, 'R04; input 67')
    for rid, endseq in [('sol-0530a9827c2c',69),('terra-2f66dbe7f15d',75)]:
        events=[json.loads(x) for x in (SESSION/rid/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        seen=[e for e in events if e['kind']=='evidence.retrieved' and e['seq']<endseq and
              e['payload'].get('evidence',{}).get('evidence_id')=='E_SNAPSHOT']
        record(rid+'-preceding-snapshot-retrieval', bool(seen), rid.startswith('terra'),
               'R04; bounded completed trace prefix before market report, not a claim of private reliance')

    # Explicit hand-authored sufficient sets. AND within each set, OR across sets.
    # F is common fixture-author admissibility, N is accepted normalization.
    justifications=[{'F','CSV','N'},{'F','SNAP','N'}]
    def active_sets(states):
        return [sorted(s) for s in justifications if all(states.get(x)=='valid' for x in s)]
    base={x:'valid' for x in ['F','CSV','N','SNAP']}
    record('two-alternatives', len(active_sets(base)), 2, 'Hypothetical justifications based on R01 sources', 'abstract counterexample')
    changed=dict(base,SNAP='invalid')
    record('invalidate-one-route', len(active_sets(changed)), 1, 'CSV route survives; no independence inferred', 'abstract counterexample')
    history=[dict(context='K0', states=dict(base), active=active_sets(base)),
             dict(context='K1', states=dict(changed), active=active_sets(changed),
                  cause='hypothetical snapshot withdrawal; not observed in frozen run')]
    record('historical-context-retained', len(history[0]['active']), 2,
           'K0 remains stored after K1 recalculation', 'abstract counterexample')
    record('current-context-recorded', len(history[1]['active']), 1,
           'K1 records path loss separately; conclusion still supported by CSV under these assumptions', 'abstract counterexample')
    record('invalidate-common-root', len(active_sets(dict(base,F='invalid'))), 0, 'Shared F disables both routes', 'abstract counterexample')
    record('invalidate-normalization', len(active_sets(dict(base,N='invalid'))), 0, 'Both rely on the normalized claim mapping', 'abstract counterexample')
    record('pending-one-route', len(active_sets(dict(base,SNAP='pending'))), 1, 'Pending route is not counted as established; CSV still valid', 'abstract counterexample')
    record('no-grounded-prerequisites', bool(active_sets({})), False, 'No supplied prerequisite states; not a general cycle-detection test', 'abstract counterexample')
    positive=True
    negative=True
    record('conflict-retained', (positive,negative), (True,True), 'A contrary admissible witness coexists; do not resolve by source count', 'abstract counterexample')
    # Half-open intervals are an explicit example convention, not a universal rule.
    def disjoint(a,b):
        return a[1] <= b[0] or b[1] <= a[0]
    record('rounded-compatible', disjoint((Decimal('2539.5'),Decimal('2540.5')),
                                         (Decimal('2540'),Decimal('2540.01'))), False,
           'Counterexample: overlapping rounding intervals are not contradiction proof', 'abstract counterexample')
    record('rounded-incompatible', disjoint((Decimal('2539.5'),Decimal('2540.5')),
                                           (Decimal('2541'),Decimal('2541.01'))), True,
           'Counterexample: explicit nonoverlapping intervals; same tuple assumed', 'abstract counterexample')
    output=dict(status='bounded local mechanism demonstration, not independent evaluation',
                passed_mechanism_assertions=sum(r.get('result')=='PASS' for r in results),
                raw_inputs_modified=False, model_calls=0, network_calls=0, results=results,
                hypothetical_history=history,
                limitations=['No semantic parser or causal reliance inference',
                             'No calibrated confidence, exhaustive coverage or quality score',
                             'Justification sets are hypothetical and not extracted agent dependencies'])
    dest=LANE/'notes/demo-results.json'
    dest.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='results'}))


if __name__=='__main__':
    main()
