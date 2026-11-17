import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import secrets
from threading import Event, Timer
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, update
from sqlalchemy.exc import OperationalError

from app.modules.notification.models import Notification
from app.platform.config import get_settings
from app.platform.health import ServiceHeartbeat, record_worker
from app.platform.identifiers import utcnow
from app.platform.tasks import Task
from backend.tests.support import household


def test_readiness_distinguishes_worker_state_and_dependencies(system, monkeypatch):
    from app.platform import health
    client, _, factory, _ = system

    async def clear():
        async with factory() as db:
            await db.execute(delete(ServiceHeartbeat))
            await db.commit()

    asyncio.run(clear())
    missing = client.get('/health/ready', headers={'X-Request-ID': 'ready-missing'})
    assert missing.status_code == 503
    body = missing.json()
    assert body['status'] == 'not_ready'
    assert body['components']['database']['status'] == 'ok'
    assert body['components']['migrations']['status'] == 'ok'
    assert body['components']['storage']['status'] == 'ok'
    assert body['components']['worker']['status'] == 'missing'
    assert body['components']['tasks']['dead'] == 0

    async def seed():
        async with factory() as db:
            await record_worker(db, 'integration-worker', utcnow())
            await db.commit()

    asyncio.run(seed())
    ready = client.get('/health/ready', headers={'X-Request-ID': 'ready-ok'})
    assert ready.status_code == 200
    assert ready.json()['status'] == 'ready'
    assert ready.json()['components']['worker']['status'] == 'ok'

    current_head = health.EXPECTED_MIGRATION_HEAD
    monkeypatch.setattr(health, 'EXPECTED_MIGRATION_HEAD', 'not-the-current-head')
    mismatch = client.get('/health/ready')
    assert mismatch.status_code == 503
    assert mismatch.json()['components']['database']['status'] == 'ok'
    assert mismatch.json()['components']['migrations']['status'] == 'mismatch'
    monkeypatch.setattr(health, 'EXPECTED_MIGRATION_HEAD', current_head)

    async def stale():
        async with factory() as db:
            await db.execute(update(ServiceHeartbeat).values(last_seen_at=utcnow() - timedelta(minutes=5)))
            await db.commit()

    asyncio.run(stale())
    stale_response = client.get('/health/ready')
    assert stale_response.status_code == 503
    assert stale_response.json()['components']['worker']['status'] == 'stale'
    asyncio.run(clear())


def test_ops_status_authentication_and_database_unavailability(system, monkeypatch):
    from app.main import app

    client, _, _, _ = system
    family = household(client)
    path = '/internal/ops/status'
    token = secrets.token_hex(32)
    headers = {'Authorization': f'Bearer {token}'}

    @asynccontextmanager
    async def failed_database():
        raise OperationalError(None, None, RuntimeError('private database endpoint'))
        yield

    monkeypatch.delenv('OPS_STATUS_TOKEN', raising=False)
    get_settings.cache_clear()
    assert client.get(path, headers=headers).status_code == 404
    assert path not in client.get('/openapi.json').json()['paths']

    monkeypatch.setenv('OPS_STATUS_TOKEN', token)
    monkeypatch.setenv('OPS_BUILD_REVISION', '184c2dd')
    get_settings.cache_clear()
    with monkeypatch.context() as isolation:
        isolation.setattr(app.state, 'session_factory', failed_database)
        for credential in ({}, family[2], {'Authorization': f'Bearer {secrets.token_hex(32)}'}):
            refused = client.get(path, headers=credential)
            assert refused.status_code == 401
            assert refused.headers['WWW-Authenticate'] == 'Bearer'
            assert refused.headers['Cache-Control'] == 'no-store'
        assert client.post(path, headers=headers).status_code == 405
        response = client.get(path, headers=headers)
    assert response.status_code == 503 and response.headers['Cache-Control'] == 'no-store'
    assert response.json()['version']['build_revision'] == '184c2dd'
    assert response.json()['tasks'] is None and response.json()['notifications'] is None
    assert 'private database endpoint' not in response.text
    assert client.get('/health/live').status_code == 200


def test_ops_status_aggregates_operational_counts_without_record_details(system, monkeypatch):
    from app.main import app
    from app.platform.health import EXPECTED_MIGRATION_HEAD

    client, engine, _, _ = system
    home = household(client)
    now = utcnow()
    with engine.begin() as connection:
        for status in ('PENDING', 'RUNNING', 'RETRY', 'DEAD', 'SUCCEEDED'):
            connection.execute(insert(Task).values(family_id=UUID(home[0]), resource_id=uuid4(), resource_version=1,
                kind='MEMORY_INDEX', business_key='private-task-' + status, status=status,
                lease_token=uuid4() if status == 'RUNNING' else None,
                lease_until=now + timedelta(seconds=30) if status == 'RUNNING' else None))
        for channel, status, failure, expired in (
                ('PUSH', 'FAILED', 'PROVIDER_REJECTED', False),
                ('PUSH', 'FAILED', 'DELIVERY_UNKNOWN', False),
                ('PUSH', 'FAILED', 'PROVIDER_REJECTED', True),
                ('SMS', 'READ', 'PROVIDER_DELIVERY_FAILED', False),
                ('SMS', 'SENT', None, False)):
            connection.execute(insert(Notification).values(channel=channel, status=status, error_code=failure,
                summary='private-notification-body', policy_version='test', created_at=now - timedelta(days=2),
                retention_until=now + timedelta(days=-1 if expired else 1), dispatch_deadline=now,
                recipient_user_id=UUID(home[1])))

    token = secrets.token_hex(32)
    monkeypatch.setenv('OPS_STATUS_TOKEN', token)
    monkeypatch.setenv('OPS_BUILD_REVISION', '')
    get_settings.cache_clear()
    before = app.state.request_metrics.snapshot()
    response = client.get('/internal/ops/status', headers={'Authorization': f'Bearer {token}'})
    assert app.state.request_metrics.snapshot() == before
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    assert response.json() == {
        'status': 'ok',
        'version': {'api': app.version, 'build_revision': None, 'expected_migration': EXPECTED_MIGRATION_HEAD},
        'tasks': {'pending': 1, 'running': 1, 'retry': 1, 'dead': 1},
        'notifications': {'IN_APP': {'failed': 0, 'unknown': 0}, 'PUSH': {'failed': 1, 'unknown': 1},
                          'SMS': {'failed': 1, 'unknown': 0}, 'PHONE': {'failed': 0, 'unknown': 0}},
    }
    assert all(secret not in response.text for secret in (token, home[0], 'private-notification-body', 'private-task-'))


def test_ops_status_times_out_before_database_cleanup(system, monkeypatch):
    from app.platform import ops_status

    client, _, _, _ = system
    release, finished = Event(), Event()

    async def stalled_read(factory):
        try:
            await asyncio.Future()
        finally:
            await asyncio.to_thread(release.wait)
            finished.set()

    token = secrets.token_hex(32)
    monkeypatch.setenv('OPS_STATUS_TOKEN', token)
    monkeypatch.setattr(ops_status, 'QUERY_TIMEOUT', 0.025)
    monkeypatch.setattr(ops_status, 'read_counts', stalled_read)
    get_settings.cache_clear()
    fallback = Timer(3, release.set)
    fallback.start()
    try:
        response = client.get('/internal/ops/status', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 503
        assert not finished.is_set()
    finally:
        release.set()
        fallback.cancel()
    assert finished.wait(3)
