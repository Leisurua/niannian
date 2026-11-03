import asyncio
import json

import httpx
import pytest

from app.platform.monitor import (
    AlertMonitor, MonitorSettings, RateWindow, load_state, probe, publish, save_state,
)


def settings(tmp_path, **values):
    return MonitorSettings(ntfy_url='https://ops.invalid/private-topic',
        ntfy_token_file=tmp_path / 'token', state_file=tmp_path / 'state.json', **values)


def test_alert_retry_restart_unknown_and_recovery_do_not_spam(tmp_path):
    async def exercise():
        config = settings(tmp_path, failure_samples=2, recovery_samples=2, retry_seconds=1, repeat_seconds=60)
        sent = []
        failing = True
        async def send(code, status):
            sent.append((code, status))
            return not failing
        monitor = AlertMonitor(config)
        await monitor.update({'WORKER_UNAVAILABLE': True}, 10, send)
        assert not sent
        await monitor.update({'WORKER_UNAVAILABLE': True}, 11, send)
        assert sent == [('WORKER_UNAVAILABLE', 'FIRING')]
        assert not monitor.state['WORKER_UNAVAILABLE']['active']
        failing = False
        await monitor.update({'WORKER_UNAVAILABLE': True}, 12, send)
        save_state(config.state_file, monitor.state)
        monitor = AlertMonitor(config, load_state(config.state_file))
        await monitor.update({'API_UNREACHABLE': True}, 13, send)
        await monitor.update({'WORKER_UNAVAILABLE': True}, 14, send)
        assert len(sent) == 2  # Unknown readings and restarts cannot falsely recover or repeat.
        await monitor.update({'WORKER_UNAVAILABLE': True}, 72, send)
        assert sent[-1] == ('WORKER_UNAVAILABLE', 'FIRING') and len(sent) == 3
        await monitor.update({'WORKER_UNAVAILABLE': False}, 73, send)
        assert len(sent) == 3
        await monitor.update({'WORKER_UNAVAILABLE': False}, 74, send)
        assert sent[-1] == ('WORKER_UNAVAILABLE', 'RECOVERED')
        await monitor.update({'WORKER_UNAVAILABLE': False}, 75, send)
        assert len(sent) == 4
    asyncio.run(exercise())


def test_rates_use_traffic_window_and_handle_counter_reset(tmp_path):
    config = settings(tmp_path)
    window = RateWindow()
    assert window.observe((100, 1, 100), 0, config)['HTTP_ERRORS'] is None
    assert window.observe((110, 2, 140), 30, config)['HTTP_ERRORS'] is None
    assert window.observe((120, 3, 180), 60, config) == {'HTTP_ERRORS': True, 'HTTP_LATENCY': True}
    assert window.observe((130, 3, 181), 400, config)['HTTP_ERRORS'] is None
    assert window.observe((0, 0, 0), 430, config)['HTTP_LATENCY'] is None


def test_probes_classify_dependencies_dead_backlog_and_unreachable_api(tmp_path):
    async def exercise():
        config = settings(tmp_path)
        unavailable = False
        def transport(request):
            if unavailable:
                raise httpx.ConnectError('synthetic-private-provider-body', request=request)
            if request.url.path == '/metrics':
                return httpx.Response(200, text='nianian_http_requests_total 0\n'
                    'nianian_http_errors_total 0\nnianian_http_request_duration_seconds_sum 0\n')
            return httpx.Response(503, json={'components': {
                'api': {'status': 'ok'}, 'database': {'status': 'ok'}, 'migrations': {'status': 'mismatch'},
                'storage': {'status': 'unavailable'}, 'worker': {'status': 'stale'},
                'tasks': {'status': 'degraded', 'dead': 1, 'pending': 100, 'running': 0, 'retry': 0}}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            result = await probe(client, config, RateWindow(), 10)
            assert result['API_UNREACHABLE'] is False and result['DATABASE_UNAVAILABLE'] is False
            for code in ('MIGRATIONS_UNREADY', 'STORAGE_UNAVAILABLE', 'WORKER_UNAVAILABLE', 'DEAD_TASKS', 'TASK_BACKLOG'):
                assert result[code] is True
            unavailable = True
            result = await probe(client, config, RateWindow(), 20)
            assert result['API_UNREACHABLE'] is True
            assert all(value is None for code, value in result.items() if code != 'API_UNREACHABLE')
    asyncio.run(exercise())


def test_private_publish_requires_acceptance_and_does_not_log_secrets(tmp_path, caplog):
    async def exercise():
        config = settings(tmp_path)
        token = 'fictional-operations-token'
        accepted = False
        def transport(request):
            assert request.headers['authorization'] == 'Bearer ' + token
            assert b'WORKER_UNAVAILABLE' in request.content
            assert b'family' not in request.content and b'private-topic' not in request.content
            return httpx.Response(200 if accepted else 403, json={'id': 'synthetic-message-id'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            assert not await publish(client, config, token, 'WORKER_UNAVAILABLE', 'FIRING')
            accepted = True
            assert await publish(client, config, token, 'WORKER_UNAVAILABLE', 'RECOVERED')
        from app.platform.logging import StructuredFormatter
        output = '\n'.join(StructuredFormatter().format(record) for record in caplog.records)
        assert token not in output and 'private-topic' not in output
    asyncio.run(exercise())


def test_corrupt_state_is_not_silently_discarded(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text(json.dumps({'WORKER_UNAVAILABLE': {'active': 'false'}}), encoding='utf-8')
    with pytest.raises(ValueError):
        load_state(path)
