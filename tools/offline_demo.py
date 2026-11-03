"""Portable synthetic mechanism demo; no private corpus, budgets or network."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def source_hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'procedural_loop').rglob('*'))
            if p.is_file() and p.suffix in ('.py', '.json') and '__pycache__' not in p.parts}

def run(output):
    from procedural_loop.runner import run_one, signatures
    before = source_hashes()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    summaries = [run_one(shape, output / shape, 'public-demo:' + shape) for shape in ('single', 'multi')]
    if signatures(output / 'single') != signatures(output / 'multi'):
        raise AssertionError('Adapter result signatures differ')
    if before != source_hashes():
        raise AssertionError('Packaged implementation/fixture source changed')
    result = {'status': 'COMPLETE', 'scope': 'authored synthetic procedure only',
        'shapes': summaries, 'packaged_source_hashes': before, 'source_preservation': 'PASS',
        'model_calls': 0, 'network_calls': 0, 'trade_execution': False,
        'private_historical_inputs_used': False,
        'limitations': ['Scripted host, no live agent enforcement or financial suitability.',
            'This guard covers packaged demo sources, not excluded historical/budget files.']}
    (output / 'demo-manifest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('OFFLINE DEMO COMPLETE: ' + str(output))
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.output)
