import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from threading import Event
from zipfile import ZipFile

import pytest
from sqlalchemy import text

from app.modules.account import exports
from app.platform.config import get_settings
from backend.tests.support import URL, household, post

pytestmark = pytest.mark.skipif(not URL, reason='Disposable PostgreSQL required')


def test_async_export_idempotency_owner_isolation_and_private_download(system):
    client, engine, factory, storage = system
    home = household(client)
    path = '/v1/me/exports'
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: post(client, path, home[4], key='export-once'), range(2)))
    assert [r.status_code for r in replies] == [202, 202]
    assert replies[0].json()['id'] == replies[1].json()['id']
    job_id = replies[0].json()['id']
    location = path + '/' + job_id
    assert replies[0].headers['cache-control'] == 'no-store'
    assert client.get(location + '/download', headers=home[4]).status_code == 409
    assert client.get(location, headers=home[2]).status_code == 404
    assert client.post(location + '/retry', headers=home[2]).status_code == 404
    assert asyncio.run(exports.process_one(factory, storage, get_settings()))
    status = client.get(location, headers=home[4]).json()
    assert status['status'] == 'READY' and 'object_key' not in status
    downloaded = client.get(status['download_url'], headers=home[4])
    assert downloaded.status_code == 200 and downloaded.headers['cache-control'] == 'no-store'
    with ZipFile(BytesIO(downloaded.content)) as archive:
        assert json.loads(archive.read('account.json'))['user']['id'] == home[3]
    assert client.get(status['download_url'], headers=home[2]).status_code == 404
    with engine.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM account_export')).scalar() == 1
        conn.execute(text("UPDATE account_export SET expires_at=now()-interval '1 minute', cleanup_after=now()-interval '1 minute'"))
    assert client.get(location + '/download', headers=home[4]).status_code == 410
    assert asyncio.run(exports.process_one(factory, storage, get_settings()))
    assert not storage.objects


def test_retry_exhaustion_manual_retry_and_account_deletion_purge(system, monkeypatch):
    from backend.tests.integration.test_account_lifecycle import request_delete
    client, engine, factory, storage = system
    home = household(client)
    result = post(client, '/v1/me/exports', home[4], key='export-retry').json()
    original_write = storage.write
    async def fail(*_):
        raise RuntimeError('synthetic-private-storage-detail')
    monkeypatch.setattr(storage, 'write', fail)
    for _ in range(3):
        assert asyncio.run(exports.process_one(factory, storage, get_settings()))
        with engine.begin() as conn:
            conn.execute(text('UPDATE account_export SET retry_at=now()'))
    location = '/v1/me/exports/' + result['id']
    assert client.get(location, headers=home[4]).json()['status'] == 'FAILED'
    assert 'synthetic-private' not in client.get(location, headers=home[4]).text
    assert client.post(location + '/retry', headers=home[4]).status_code == 202
    monkeypatch.setattr(storage, 'write', original_write)
    assert asyncio.run(exports.process_one(factory, storage, get_settings()))
    assert storage.objects
    request_delete(client, home[4])
    assert client.get(location + '/download', headers=home[4]).status_code == 401
    with engine.begin() as conn:
        assert conn.execute(text('SELECT status FROM account_export')).scalar() == 'CANCELLED'
        conn.execute(text("UPDATE account_export SET cleanup_after=now()-interval '1 minute', retry_at=now()"))
    assert asyncio.run(exports.process_one(factory, storage, get_settings()))
    assert not storage.objects


def test_retry_then_account_deletion_purges_unconfirmed_write(system, monkeypatch):
    from backend.tests.integration.test_account_lifecycle import request_delete

    client, engine, factory, storage = system
    home = household(client)
    job = post(client, '/v1/me/exports', home[4], key='unconfirmed-write').json()
    original_write = storage.write

    async def write_then_fail(*args):
        await original_write(*args)
        raise RuntimeError('Storage write was not acknowledged')

    monkeypatch.setattr(storage, 'write', write_then_fail)
    for _ in range(3):
        assert asyncio.run(exports.process_one(factory, storage, get_settings()))
        with engine.begin() as conn:
            conn.execute(text('UPDATE account_export SET retry_at=now()'))
    assert storage.objects
    retry = client.post('/v1/me/exports/' + job['id'] + '/retry', headers=home[4])
    assert retry.status_code == 202 and retry.json()['attempts'] == 0
    request_delete(client, home[4])

    with engine.begin() as conn:
        conn.execute(text("UPDATE account_export SET cleanup_after=now()-interval '1 minute', retry_at=now()"))
    assert asyncio.run(exports.process_one(factory, storage, get_settings()))
    assert not storage.objects


def test_status_polling_is_available_while_worker_generates(system, monkeypatch):
    client, _, factory, storage = system
    home = household(client)
    result = post(client, '/v1/me/exports', home[4], key='visible-running').json()
    entered, release = Event(), Event()
    original = storage.write
    async def waiting(*args):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        await original(*args)
    monkeypatch.setattr(storage, 'write', waiting)
    with ThreadPoolExecutor(max_workers=2) as pool:
        work = pool.submit(lambda: asyncio.run(exports.process_one(factory, storage, get_settings())))
        try:
            assert entered.wait(3)
            query = pool.submit(lambda: client.get('/v1/me/exports/' + result['id'], headers=home[4]))
            response = query.result(timeout=2)
            assert response.status_code == 200 and response.json()['status'] == 'RUNNING'
        finally:
            release.set()
        assert work.result(timeout=5)
