"""Verify W7 in a clean hashed snapshot; --integration requires isolated DB/storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_week4 import snapshot

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='New empty ASCII directory outside the repository')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/week7/verification')
    parser.add_argument('--integration', action='store_true', help='Full backend/tests + tests, after isolated migrations')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if (source.is_relative_to(ROOT) or ROOT.is_relative_to(source) or not str(source).isascii()
            or output.is_relative_to(source) or source.is_relative_to(output)
            or source.exists() and (not source.is_dir() or any(source.iterdir()))):
        parser.error('Source must be a new empty ASCII directory outside repository and output')
    source.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    hashes = snapshot(source)
    (output / 'source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    env = {**os.environ, 'PYTHONUTF8': '1', 'APP_ENV': 'test', 'PROVIDER_MODE': 'mock',
        'PYTHONPATH': os.pathsep.join((str(source / 'backend'), str(source)))}
    checks = []
    report = output / 'tests.xml'
    report.unlink(missing_ok=True)
    test_roots = (['backend/tests', 'tests'] if args.integration else
        ['backend/tests/unit', 'backend/tests/contract', 'backend/tests/test_openapi_source.py', 'tests/security'])
    commands = {
        'lint': [sys.executable, '-m', 'ruff', 'check', 'backend', 'scripts', 'tests'],
        'tests': [sys.executable, '-u', '-m', 'pytest', *test_roots, '-q', '-p', 'no:cacheprovider',
            '-k', 'not test_built_apks_contain_no_secret_patterns', '--tb=short', '--show-capture=no',
            '--basetemp', str(output / 'pytest'),
            '--junitxml', str(report)],
    }
    for name, command in commands.items():
        try:
            with (output / f'{name}.txt').open('w', encoding='utf-8') as log:
                process = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                    timeout=600, check=False)
            status = 'PASS' if process.returncode == 0 else 'FAIL'
        except (OSError, subprocess.TimeoutExpired):
            status = 'NOT VERIFIED'
        checks.append(dict(name=name, status=status))
        print(f'{status}: {name}', flush=True)
    try:
        suites = list(ET.parse(report).getroot().iter('testsuite'))
        counts = {key: sum(int(item.get(key, 0)) for item in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
        status = ('FAIL' if counts['failures'] or counts['errors'] else
            'NOT VERIFIED' if not counts['tests'] or counts['skipped'] else 'PASS')
        checks.append(dict(name='test-inventory', status=status, **counts))
    except (OSError, ValueError, ET.ParseError):
        checks.append(dict(name='test-inventory', status='NOT VERIFIED'))
    unchanged = all((ROOT / name).is_file() and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
        and hashlib.sha256((source / name).read_bytes()).hexdigest() == value for name, value in hashes.items())
    checks.append(dict(name='source-equality', status='PASS' if unchanged else 'FAIL'))
    status = ('FAIL' if any(c['status'] == 'FAIL' for c in checks) else
        'NOT VERIFIED' if any(c['status'] == 'NOT VERIFIED' for c in checks) else 'PASS')
    result = dict(scope='Week 7 backend' if args.integration else 'Week 7 unit/contract/source', status=status, checks=checks,
        excluded=([] if args.integration else ['PostgreSQL/worker/storage integration']) +
            ['Android/APK/device: separate evidence required', 'Real providers/audio', 'Remote CI'])
    (output / 'summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return {'PASS': 0, 'FAIL': 1, 'NOT VERIFIED': 2}[status]


if __name__ == '__main__':
    raise SystemExit(main())
