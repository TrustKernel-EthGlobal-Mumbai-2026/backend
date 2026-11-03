"""Read-only manifest/hash and credential-pattern check of staged public files."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'openai_key_shape': re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}'),
    'github_token_shape': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,})'),
    'aws_access_key_shape': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential_url': re.compile(r'https?://[^\s/@:]+:[^\s/@]+@'),
    'machine_specific_user_path': re.compile(r'(?i)(?:/?[A-Z]:[/\\]Users[/\\][^/\\\s\"\x27]+|/Users/[^/\s]+)'),
    'assigned_credential_literal': re.compile(r'(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key)[\"\x27]?\s*[:=]\s*[\"\x27][A-Za-z0-9+/=_-]{16,}[\"\x27]'),
}

def main():
    manifest = json.loads((ROOT / 'PACKAGING_MANIFEST.json').read_text(encoding='utf-8'))
    exceptions = {(r['path'], r['rule'], r['line'], r['match_sha256']) for r in manifest.get('reviewed_test_fixture_matches', [])}
    issues = []
    for row in manifest['files']:
        path = ROOT / row['destination']
        if not path.resolve().is_relative_to(ROOT.resolve()) or path.is_symlink():
            issues.append({'path': row['destination'], 'rule': 'path_escape_or_symlink'})
            continue
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['staged_sha256']:
            issues.append({'path': row['destination'], 'rule': 'hash_mismatch'})
        text = data.decode('utf-8')
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                fingerprint = hashlib.sha256(match.group().encode()).hexdigest()
                line = text.count('\n', 0, match.start()) + 1
                if (row['destination'], rule, line, fingerprint) not in exceptions:
                    issues.append({'path': row['destination'], 'rule': rule,
                        'line': text.count('\n', 0, match.start()) + 1, 'match_sha256': fingerprint})
    print(json.dumps({'status': 'PASS' if not issues else 'FAIL', 'files': len(manifest['files']),
        'issues': issues, 'scope': 'manifest-listed public files only; no credential/cache/budget reads'}, indent=2))
    if issues:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
