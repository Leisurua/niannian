"""Verify Week 4 in a content-hashed source snapshot, excluding local tool artifacts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from verify_week3 import disposable

ROOT = Path(__file__).resolve().parents[1]


def snapshot(destination):
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    hashes = {}
    for value in set(paths.decode('utf-8').split('\0')) - {''}:
        source = ROOT / value
        if not source.is_file():
            continue
        target = destination / value
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError('Source path escaped snapshot')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[value] = hashlib.sha256(source.read_bytes()).hexdigest()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == hashes[value]
    git_dir = subprocess.check_output(['git', 'rev-parse', '--absolute-git-dir'], cwd=ROOT, text=True).strip()
    (destination / '.git').write_text('gitdir: ' + git_dir + '\n', encoding='utf-8')
    return hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/week4/verification')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    def record(name, status, **details):
        checks.append(dict(check=name, status=status, **details))
        print(status + ': ' + name, flush=True)
    def execute(name, command, cwd, env):
        try:
            with (output / (name + '.txt')).open('w', encoding='utf-8') as log:
                process = subprocess.run(command, cwd=cwd, env=env, stdout=log,
                    stderr=subprocess.STDOUT, timeout=600, check=False)
            record(name, 'PASS' if process.returncode == 0 else 'FAIL', exit_code=process.returncode)
            return process.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            record(name, 'NOT VERIFIED', reason='Command unavailable or timed out')
            return False
    with tempfile.TemporaryDirectory(prefix='niannian-week4-') as directory:
        source = Path(directory) / 'source'
        source.mkdir()
        hashes = snapshot(source)
        (output / 'source-hashes.json').write_text(json.dumps(hashes, indent=2, ensure_ascii=False), encoding='utf-8')
        env = {**os.environ, 'APP_ENV': 'test', 'PROVIDER_MODE': 'mock', 'PYTHONUTF8': '1',
            'PYTHONPATH': os.pathsep.join((str(source / 'backend'), str(source)))}
        ready = True
        for week in (2, 3):
            url = env.get(f'WEEK{week}_TEST_DATABASE_URL', '')
            if not disposable(url, week):
                record(f'week{week}-database', 'NOT VERIFIED', reason='Explicit disposable test database required')
                env.pop(f'WEEK{week}_TEST_DATABASE_URL', None)
                ready = False
            else:
                if not execute(f'week{week}-upgrade', [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                               source / 'backend', {**env, 'DATABASE_URL': url}):
                    ready = False
                    env.pop(f'WEEK{week}_TEST_DATABASE_URL', None)
        execute('lint', [sys.executable, '-m', 'ruff', 'check', 'backend', 'scripts', 'tests'], source, env)
        report = output / 'tests.xml'
        report.unlink(missing_ok=True)
        execute('tests', [sys.executable, '-m', 'pytest', 'backend/tests', 'tests', '-q', '-p', 'no:cacheprovider',
            '--tb=short', '--show-capture=no', '--basetemp', str(Path(directory) / 'pytest'),
            '--junitxml', str(report), '--ignore=backend/tests/integration/test_week3_storage.py',
            '-k', 'not test_built_apks_contain_no_secret_patterns'], source, env)
        try:
            suites = list(ET.parse(report).getroot().iter('testsuite'))
            counts = {key: sum(int(item.get(key, 0)) for item in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
            result = 'FAIL' if counts['failures'] or counts['errors'] else 'NOT VERIFIED' if counts['skipped'] or not counts['tests'] else 'PASS'
            record('test-inventory', result, **counts)
        except (OSError, ET.ParseError, ValueError):
            record('test-inventory', 'NOT VERIFIED', reason='Missing or invalid JUnit')
        if not ready:
            record('WSS-PostgreSQL', 'NOT VERIFIED', reason='Database gate not ready')
    status = 'FAIL' if any(c['status'] == 'FAIL' for c in checks) else 'NOT VERIFIED' if any(c['status'] == 'NOT VERIFIED' for c in checks) else 'PASS'
    (output / 'summary.json').write_text(json.dumps(dict(status=status, checks=checks,
        checked_at=datetime.now(timezone.utc).isoformat(),
        excluded=['Android build/device/APK', 'real MinIO (unchanged surface)', 'actual voice/provider', 'full RAG and summary']),
        indent=2, ensure_ascii=False), encoding='utf-8')
    return {'PASS': 0, 'FAIL': 1, 'NOT VERIFIED': 2}[status]


if __name__ == '__main__':
    raise SystemExit(main())
