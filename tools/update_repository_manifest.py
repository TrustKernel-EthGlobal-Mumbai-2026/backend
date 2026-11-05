"""Refresh the reviewed repository manifest, excluding private/runtime artifacts.

The manifest deliberately does not hash itself. Repository context catalogs
exclude this manifest, so index generation followed by this update is acyclic.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'README.md', 'AGENTS.md', '.gitignore', '.gitattributes', 'requirements.lock.txt', 'requirements-mcp.txt',
              'UPSTREAM.json', 'Launch-Research.ps1', 'Monitor.ps1', 'Run-30Minutes.ps1',
              'Run-Live-30Minutes.ps1', 'Run-Live-Verification.ps1', 'Run-Recorded-Verification.ps1',
              'Run-Verification-Loop.ps1', 'Smoke.ps1', 'View-Traces.ps1', 'Watch-Console.ps1'}
DIRECTORIES = {'.agents', '.github', 'bb8', 'context-index', 'continuous_verification', 'docs', 'drafts', 'examples', 'explorations',
               'fixtures', 'live_experiment', 'live_verification', 'procedural_loop', 'recorded_loop',
               'tests', 'third_party', 'tools', 'trustkernel', 'verification'}
SUFFIXES = {'.py', '.md', '.json', '.yaml', '.yml', '.html', '.cjs', '.ps1', '.txt', '.toml', '.sql'}
PRUNE = {'.git', '.context', '.venv', '__pycache__', '.pytest_cache', 'node_modules', '.local-runs',
         'runs', 'cache', '.cache', 'source-cache', 'private', 'raw', 'data', 'releases', 'upstream'}
FORBIDDEN = {'protected-before.json', 'approved-budget.sqlite', 'budget_policy.json'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def collect(root):
    root = Path(root).resolve()
    paths = []
    for current, dirs, files in os.walk(root, followlinks=False):
        current = Path(current)
        dirs[:] = sorted(d for d in dirs if d not in PRUNE and not (current/d).is_symlink()
                         and not (os.name == 'nt' and bool(getattr((current/d).lstat(), 'st_file_attributes', 0) & 0x400)))
        for name in sorted(files):
            path = current / name
            relative = path.relative_to(root).as_posix()
            if relative == 'PACKAGING_MANIFEST.json':
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('Symlink/path escape refused: ' + relative)
            parts = path.relative_to(root).parts
            if len(parts) == 1 and name not in ROOT_FILES:
                continue
            if len(parts) > 1 and parts[0] not in DIRECTORIES:
                continue
            if name.startswith('.env') or name in FORBIDDEN:
                raise ValueError('Private artifact in publishable subtree: ' + relative)
            if path.suffix not in SUFFIXES and name not in {'LICENSE', 'NOTICE', '.gitignore', '.gitattributes'}:
                if relative == 'context-index/chunks.jsonl':
                    pass
                else:
                    continue
            if path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError('Oversized public text artifact: ' + relative)
            path.read_bytes().decode('utf-8')
            paths.append((relative, path))
    return sorted(paths)


def update(root=ROOT):
    root = Path(root).resolve()
    path = root / 'PACKAGING_MANIFEST.json'
    old_bytes = path.read_bytes()
    previous = json.loads(old_bytes)
    old_rows = {r['destination']: r for r in previous['files']}
    rows = []
    for relative, source in collect(root):
        data = source.read_bytes()
        digest = sha(data)
        old = old_rows.get(relative)
        if old and old['staged_sha256'] == digest:
            row = dict(old)
        else:
            row = {'destination': relative, 'source_ref': 'repository-authoring/' + relative,
                   'source_sha256': digest, 'staged_sha256': digest, 'staged_bytes': len(data),
                   'treatment': 'repository_handoff_addition' if not old else 'repository_handoff_adaptation',
                   'workstream': relative.split('/')[0] if '/' in relative else 'repository-entrypoint'}
            if old:
                row['previous_staged_sha256'] = old['staged_sha256']
                row['previous_source_ref'] = old['source_ref']
        rows.append(row)
    manifest = {'profile': 'trustkernel-repository-handoff-1', 'status': 'REVIEWED_REPOSITORY_CONTENT',
                'base_export': previous.get('base_export', {'profile': previous['profile'], 'manifest_sha256': sha(old_bytes)}),
                'files': rows, 'reviewed_test_fixture_matches': previous.get('reviewed_test_fixture_matches', []),
                'upstream_commit': 'c4544913a14ed3df5f1ed7b9e8483270ce20682a', 'upstream_license': 'Apache-2.0',
                'new_code_license': 'PENDING_USER_CHOICE', 'private_raw_evidence_included': False,
                'bb8_provenance': 'bb8/SNAPSHOT.json', 'context_entrypoint': 'README.md',
                'derived_cache_excluded': '.context/', 'index_manifest_cycle_exclusion': 'PACKAGING_MANIFEST.json'}
    # Reuse the same patterns/exact negative-fixture acknowledgements as publication checks.
    spec = importlib.util.spec_from_file_location('repository_export_check', root/'tools/check_export.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    exceptions = {(r['path'], r['rule'], r['line'], r['match_sha256']) for r in manifest['reviewed_test_fixture_matches']}
    findings = []
    for row in rows:
        text = (root/row['destination']).read_bytes().decode('utf-8')
        for rule, pattern in checker.PATTERNS.items():
            for match in pattern.finditer(text):
                key = (row['destination'], rule, text.count('\n', 0, match.start())+1, sha(match.group().encode()))
                if key not in exceptions:
                    findings.append({'path': key[0], 'rule': rule, 'line': key[2], 'match_sha256': key[3]})
    if findings:
        raise ValueError('Unreviewed credential/path-shaped literals: ' + json.dumps(findings))
    output = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    path.write_bytes(output)
    return {'status': 'PASS', 'files': len(rows), 'manifest_sha256': sha(output),
            'private_evidence_included': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(update(args.root), indent=2))
