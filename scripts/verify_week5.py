"""W5 reproducible source snapshot, guarded PostgreSQL/MinIO regression and optional Android build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_week3 import disposable
from verify_week4 import snapshot

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Dedicated ASCII-only source copy, outside repository')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/week5/verification')
    parser.add_argument('--android', action='store_true')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if source.is_relative_to(ROOT) or ROOT.is_relative_to(source) or not str(source).isascii():
        parser.error('Use a dedicated ASCII directory outside the repository')
    source.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    previous_file = output / 'source-hashes.json'
    previous = json.loads(previous_file.read_text(encoding='utf-8')) if previous_file.exists() else {}
    hashes = snapshot(source)
    for name in previous.keys() - hashes.keys():
        obsolete = (source / name).resolve()
        if not obsolete.is_relative_to(source):
            raise ValueError('Obsolete snapshot path escaped source directory')
        if obsolete.is_file():
            if hashlib.sha256(obsolete.read_bytes()).hexdigest() != previous[name]:
                raise ValueError('Refusing to erase a modified snapshot source file')
            obsolete.unlink()
    (output / 'source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    env = {**os.environ, 'APP_ENV': 'test', 'PROVIDER_MODE': 'mock', 'PYTHONUTF8': '1',
        'PYTHONPATH': os.pathsep.join((str(source / 'backend'), str(source)))}
    checks = []

    def record(name, status, **detail):
        checks.append(dict(name=name, status=status, **detail))
        print(f'{status}: {name}', flush=True)

    def run(name, command, cwd=source, environment=None, timeout=600):
        try:
            with (output / f'{name}.txt').open('w', encoding='utf-8') as log:
                result = subprocess.run(command, cwd=cwd, env=environment or env, stdout=log,
                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
            record(name, 'PASS' if result.returncode == 0 else 'FAIL', exit_code=result.returncode)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            record(name, 'NOT VERIFIED', reason='Command unavailable or timed out')
            return False

    def inventory(name, reports):
        suites = []
        try:
            for file in reports:
                root = ET.parse(file).getroot()
                suites.extend(root.iter('testsuite'))
            counts = {key: sum(int(item.get(key, 0)) for item in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
            status = 'FAIL' if counts['failures'] or counts['errors'] else 'NOT VERIFIED' if not counts['tests'] or counts['skipped'] else 'PASS'
            record(name, status, **counts)
        except (OSError, ET.ParseError, ValueError):
            record(name, 'NOT VERIFIED', reason='Missing or unreadable JUnit report')

    for week in (2, 3):
        url = env.get(f'WEEK{week}_TEST_DATABASE_URL', '')
        if disposable(url, week):
            run(f'week{week}-upgrade', [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                source / 'backend', {**env, 'DATABASE_URL': url})
        else:
            env.pop(f'WEEK{week}_TEST_DATABASE_URL', None)
            record(f'week{week}-database', 'NOT VERIFIED', reason='Explicit disposable database URL required')
    run('ruff', [sys.executable, '-m', 'ruff', 'check', 'backend', 'scripts', 'tests'])
    report = output / 'backend-tests.xml'
    report.unlink(missing_ok=True)
    run('backend-tests', [sys.executable, '-m', 'pytest', 'backend/tests', 'tests', '-q', '-p', 'no:cacheprovider',
        '--tb=line', '--show-capture=no', '--basetemp', str(output / 'pytest'), '--junitxml', str(report),
        '-k', 'not test_built_apks_contain_no_secret_patterns'])
    inventory('backend-inventory', [report])
    if args.android:
        gradle = env.get('GRADLE_EXECUTABLE')
        if gradle and Path(gradle).is_file():
            run('android-build', [gradle, '--offline', '--no-daemon', 'build'], source / 'android', timeout=900)
            reports = list((source / 'android').glob('*/build/test-results/*/TEST-*.xml'))
            target = output / 'android-tests'
            target.mkdir(exist_ok=True)
            for file in reports:
                shutil.copyfile(file, target / (file.parts[-5] + '-' + file.parent.name + '-' + file.name))
            inventory('android-inventory', reports)
            lints = list((source / 'android').glob('*/build/reports/lint-results-*.xml'))
            errors = sum(item.get('severity') in ('Error', 'Fatal') for file in lints for item in ET.parse(file).getroot().iter('issue'))
            record('android-lint', 'FAIL' if errors else 'PASS' if lints else 'NOT VERIFIED', reports=len(lints), errors=errors)
            unchanged = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value ==
                hashlib.sha256((source / name).read_bytes()).hexdigest() for name, value in hashes.items() if name.startswith('android/'))
            record('android-source-equality', 'PASS' if unchanged else 'FAIL')
            apks = list((source / 'android').glob('app-*/build/outputs/apk/*/*/*.apk'))
            destination = output / 'apks'
            destination.mkdir(exist_ok=True)
            for file in apks:
                shutil.copyfile(file, destination / file.name)
            run('apk-scan', [sys.executable, '-m', 'pytest', 'tests/security/test_artifact_scan.py', '-q', '-p', 'no:cacheprovider',
                '-k', 'test_built_apks_contain_no_secret_patterns', '--tb=line', '--show-capture=no', '--junitxml', str(output / 'apk-scan.xml')],
                environment={**env, 'NIANNIAN_REQUIRE_APKS': '1'})
        else:
            record('android', 'NOT VERIFIED', reason='Set GRADLE_EXECUTABLE to an installed Gradle 8.11.1 executable')
    status = 'FAIL' if any(c['status'] == 'FAIL' for c in checks) else 'NOT VERIFIED' if any(c['status'] == 'NOT VERIFIED' for c in checks) else 'PASS'
    (output / 'summary.json').write_text(json.dumps(dict(status=status, scope='Week 5 backend' + (' and Android' if args.android else ''), checks=checks,
        excluded=['Named-device acceptance', 'real AI providers', 'remote CI', 'release signing'] +
        ([] if args.android else ['Android build/JVM/lint/APK: separate run required'])), indent=2), encoding='utf-8')
    return {'PASS': 0, 'FAIL': 1, 'NOT VERIFIED': 2}[status]


if __name__ == '__main__':
    raise SystemExit(main())
