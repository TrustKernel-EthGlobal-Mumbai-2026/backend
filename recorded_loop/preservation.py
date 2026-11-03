"""Read-only guards for historical corpus and the first completed loop."""
import hashlib
import json
from pathlib import Path

from procedural_loop.preservation import protected_hashes, ROOT

FIRST = ROOT/'runs/verification-loop-20261102T175357Z-2a96a2e5'


def capture():
    hashes=protected_hashes()
    first=json.loads((FIRST/'experiment.json').read_text(encoding='utf-8'))
    for path,expected in first['source_hashes'].items():
        actual=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('FROZEN_FIRST_LOOP_CODE_CHANGED:'+path)
        hashes[path]=actual
    for path in sorted(FIRST.rglob('*')):
        # Viewer service lifecycle files may change while inspecting; they are not experiment input.
        if path.is_file() and path.name not in {'viewer.log','viewer-errors.log','viewer.pid'}:
            hashes[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
    launcher=ROOT/'Run-Verification-Loop.ps1'
    hashes[str(launcher.relative_to(ROOT))]=hashlib.sha256(launcher.read_bytes()).hexdigest()
    return hashes


def assert_preserved(before):
    if capture()!=before:raise ValueError('PROTECTED_RECORDED_OR_FIRST_LOOP_ASSET_CHANGED')
    return {'status':'PASS','unchanged_files':len(before)}
