"""Read-only preservation gate for the authorized local extraction run."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path(__file__).with_name('protected-before.json')


def verify():
    expected = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    for relative, digest in expected.items():
        target = (ROOT / relative).resolve()
        if not target.is_relative_to(ROOT.resolve()) or not target.is_file():
            raise ValueError('PROTECTED_FILE_MISSING_OR_OUTSIDE_PROJECT:' + relative)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError('PROTECTED_FILE_CHANGED:' + relative)
    return {'status': 'PASS', 'protected_files_unchanged': len(expected),
            'budget_sha256': expected['runs/approved-budget.sqlite'],
            'scope': 'Byte-identical historical inputs/code, original live corpus and cumulative budget; no mutation authorized.'}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
