"""Run Week 3 backend gates against explicitly disposable PostgreSQL databases."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]


def disposable(url, week):
    try:
        value = make_url(url)
        return value.drivername == 'postgresql+psycopg' and not value.query and re.fullmatch(
            rf'[A-Za-z0-9_]+_week{week}_test', value.database or '') is not None
    except (ValueError, ArgumentError):
        return False


def run(output, *, postgres_only=False):
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    env = {**os.environ, 'APP_ENV': 'test', 'PROVIDER_MODE': 'mock', 'PYTHONUTF8': '1', 'PYTHONPATH': str(ROOT/'backend')}
    def record(name, status, **details):
        checks.append(dict(check=name, status=status, **details))
        print(status + ': ' + name, flush=True)
    def execute(name, command, cwd=ROOT, environment=None):
        try:
            with (output/(name+'.txt')).open('w', encoding='utf-8') as log:
                result = subprocess.run(command, cwd=cwd, env=environment or env, stdout=log,
                    stderr=subprocess.STDOUT, timeout=600, check=False)
            record(name, 'PASS' if result.returncode == 0 else 'FAIL', exit_code=result.returncode)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            record(name, 'NOT VERIFIED', reason='Command unavailable or timed out')
            return False
    ready = True
    for week in (2, 3):
        url = env.get(f'WEEK{week}_TEST_DATABASE_URL', '')
        if not disposable(url, week):
            record(f'week{week}-database', 'NOT VERIFIED', reason=f'Explicit safe _week{week}_test database required')
            ready = False
        else:
            db_env = {**env, 'DATABASE_URL': url}
            ready = execute(f'week{week}-upgrade', [sys.executable, '-m', 'alembic', 'upgrade', 'head'], ROOT/'backend', db_env) and ready
            ready = execute(f'week{week}-parity', [sys.executable, '-m', 'alembic', 'check'], ROOT/'backend', db_env) and ready
    execute('lint', [sys.executable, '-m', 'ruff', 'check', 'backend', 'scripts', 'tests'])
    if not postgres_only and not env.get('WEEK3_STORAGE_CONFIG'):
        record('real-storage', 'NOT VERIFIED', reason='WEEK3_STORAGE_CONFIG must point to isolated MinIO settings')
        ready = False
    if ready:
        report = output/'backend-tests.xml'
        report.unlink(missing_ok=True)
        command = [sys.executable, '-m', 'pytest', 'backend/tests', 'tests', '-q', '-p', 'no:cacheprovider',
            '--tb=short', '--show-capture=no', '--junitxml', str(report), '-k', 'not test_built_apks_contain_no_secret_patterns']
        if env.get('WEEK3_PYTEST_TEMP'):
            command += ['--basetemp', env['WEEK3_PYTEST_TEMP']]
        if postgres_only:
            command += ['--ignore=backend/tests/integration/test_week3_storage.py']
        execute('backend-tests', command)
        try:
            suites = list(ET.parse(report).getroot().iter('testsuite'))
            counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
            status = 'FAIL' if counts['failures'] or counts['errors'] else 'NOT VERIFIED' if counts['skipped'] or not counts['tests'] else 'PASS'
            record('test-inventory', status, **counts)
        except (OSError, ET.ParseError, ValueError):
            record('test-inventory', 'NOT VERIFIED', reason='Missing or invalid current JUnit report')
    status = 'FAIL' if any(c['status']=='FAIL' for c in checks) else 'NOT VERIFIED' if any(c['status']=='NOT VERIFIED' for c in checks) else 'PASS'
    result = dict(status=status, checked_at=datetime.now(timezone.utc).isoformat(), checks=checks,
        scope='Week 3 backend PostgreSQL' if postgres_only else 'Week 3 backend PostgreSQL and real MinIO',
        excluded=['Android build/APK/device gates', 'migration rollback/backup rehearsal'] + (['real MinIO'] if postgres_only else []))
    (output/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/week3/verification')
    parser.add_argument('--postgres-only', action='store_true', help='Explicitly exclude the separate real MinIO gate')
    args = parser.parse_args()
    return {'PASS': 0, 'FAIL': 1, 'NOT VERIFIED': 2}[run(args.output.resolve(), postgres_only=args.postgres_only)['status']]


if __name__ == '__main__':
    raise SystemExit(main())
