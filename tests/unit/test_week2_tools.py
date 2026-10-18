import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('verify_week2', ROOT / 'scripts/verify_week2.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


@pytest.mark.parametrize('url', ['sqlite:///niannian_week2_test', 'postgresql+psycopg://localhost/production',
    'postgresql+psycopg://localhost/niannian_week2_test?dbname=production',
    'postgresql+psycopg://localhost/niannian_week2_test?service=shared',
    'postgresql+psycopg://localhost/niannian_week2_test?options=-csearch_path=shared',
    'postgresql+psycopg://localhost/niannian_week2_test?x=1',
    'postgresql+psycopg://localhost/', 'not-a-database-url'])
def test_disposable_database_guard(url):
    assert not verify.disposable_database(url)


def test_explicit_disposable_database_is_allowed():
    assert verify.disposable_database('postgresql+psycopg://localhost/niannian_week2_test')


@pytest.mark.parametrize('report', [None, '<bad', '<testsuites/>',
    '<testsuites><testsuite tests="1" skipped="1"/></testsuites>'])
def test_missing_empty_invalid_or_skipped_report_cannot_pass(monkeypatch, tmp_path, report):
    monkeypatch.setenv('WEEK2_TEST_DATABASE_URL', 'postgresql+psycopg://localhost/niannian_week2_test')
    (tmp_path / 'backend-tests.xml').write_text('<testsuites><testsuite tests="10"/></testsuites>')
    def run(command, **kwargs):
        if 'pytest' in command and report is not None:
            (tmp_path / 'backend-tests.xml').write_text(report)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(verify.subprocess, 'run', run)
    assert verify.run_checks(tmp_path)['status'] == 'NOT VERIFIED'


def test_invalid_database_never_reaches_migration_or_truncating_fixture(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv('WEEK2_TEST_DATABASE_URL', 'postgresql+psycopg://localhost/production')
    def run(command, **kwargs):
        calls.append((command, kwargs['env']))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(verify.subprocess, 'run', run)
    result = verify.run_checks(tmp_path)
    assert result['status'] == 'FAIL'
    assert not any('alembic' in command for command, _ in calls)
    tests = next((command, env) for command, env in calls if 'pytest' in command)
    assert '--ignore=backend/tests/integration' in tests[0]
    assert 'WEEK2_TEST_DATABASE_URL' not in tests[1]
    assert 'production' not in json.dumps(result)


def test_device_unavailable_is_reported_without_claiming_hardware_pass(monkeypatch, tmp_path):
    monkeypatch.delenv('WEEK2_TEST_DATABASE_URL', raising=False)
    monkeypatch.setattr(verify.subprocess, 'run', lambda command, **kwargs:
        subprocess.CompletedProcess(command, 2 if 'scripts/collect_device_baseline.py' in command else 0))
    result = verify.run_checks(tmp_path, device=True)
    assert result['status'] == 'NOT VERIFIED'
    assert all(check['status'] == 'NOT VERIFIED' for check in result['checks']
               if check['check'] in ('postgres', 'device-baseline', 'hardware-spikes'))


def test_week2_gate_collects_only_its_database_suite(monkeypatch, tmp_path):
    monkeypatch.setenv('WEEK2_TEST_DATABASE_URL', 'postgresql+psycopg://localhost/niannian_week2_test')
    monkeypatch.delenv('WEEK3_TEST_DATABASE_URL', raising=False)
    monkeypatch.delenv('PYTEST_ADDOPTS', raising=False)
    run_process = subprocess.run
    collections = []

    def run(command, **kwargs):
        if 'pytest' in command:
            collected = run_process([*command, '--collect-only', '-o', 'addopts=', '-v', '-p', 'no:cacheprovider'],
                cwd=kwargs['cwd'], env=kwargs['env'], capture_output=True, text=True, encoding='utf-8', timeout=30)
            assert collected.returncode == 0, collected.stdout + collected.stderr
            assert 'test_week2_postgres.py' in collected.stdout
            assert 'test_week3_postgres.py' not in collected.stdout
            assert 'test_week3_storage.py' not in collected.stdout
            assert 'test_week4_postgres.py' not in collected.stdout
            assert 'test_week5_postgres.py' not in collected.stdout
            assert 'test_week6_postgres.py' not in collected.stdout
            collections.append(collected.stdout)
            (tmp_path / 'backend-tests.xml').write_text('<testsuites><testsuite tests="1"/></testsuites>')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verify.subprocess, 'run', run)
    assert verify.run_checks(tmp_path)['status'] == 'PASS'
    assert len(collections) == 1
