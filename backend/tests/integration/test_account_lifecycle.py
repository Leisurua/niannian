import asyncio
from io import BytesIO
import json
import secrets
from uuid import UUID
from zipfile import ZipFile

import pytest
from sqlalchemy import text

from app.modules.account import service
from app.platform.config import get_settings
from backend.tests.support import URL, grant, household, login, memory, photo, post, reminder_body, start, upload

pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable TEST_DATABASE_URL required')


def request_delete(client, headers, token=None):
    token = token or secrets.token_urlsafe(32)
    response = client.post('/v1/me/deletion', headers=headers,
        json={'confirmation': 'DELETE_MY_ACCOUNT', 'receipt_token': token})
    assert response.status_code == 202, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json(), token


def status(client, result, token):
    return client.get('/v1/account-deletions/' + result['id'], headers={'X-Deletion-Token': token})


def test_export_owns_data_not_family_authority_or_credentials(system):
    client, engine, _, storage = system
    home = household(client)
    grant(client, home)
    mem = memory(client, home, content='fictional-own-memory')
    file_id, _ = upload(client, home, storage, mem['id'], photo())
    start(client, home)
    response = client.get('/v1/me/export', headers=home[4])
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    with ZipFile(BytesIO(response.content)) as archive:
        data = json.loads(archive.read('account.json'))
        assert data['user']['id'] == home[3]
        assert data['collections']['memory'][0]['content'] == 'fictional-own-memory'
        assert archive.read('photos/' + file_id) == storage.objects[storage.keys[-1] + '.safe']
        assert 'refresh_token_hash' not in str(data) and 'object_key' not in str(data)
        assert 'metadata_redacted' not in str(data) and 'provider_metadata' not in str(data)
    with ZipFile(BytesIO(client.get('/v1/me/export', headers=home[2]).content)) as archive:
        # Even the family creator and memory contributor cannot bulk-export the elder.
        data = json.loads(archive.read('account.json'))
        assert not data['collections']['memory']
        assert not data['collections']['file_asset']
    with engine.begin() as conn:
        conn.execute(text("UPDATE memory SET deleted_at=now(), verification_status='DELETED' WHERE id=:id"), {'id': mem['id']})
    with ZipFile(BytesIO(client.get('/v1/me/export', headers=home[4]).content)) as archive:
        assert not json.loads(archive.read('account.json'))['collections']['memory']
    assert client.get('/v1/me/export').status_code == 401


def test_deletion_revokes_erases_and_retries_files_without_touching_other_subject(system):
    client, engine, factory, storage = system
    home = household(client)
    grant(client, home)
    mem = memory(client, home)
    file_id, _ = upload(client, home, storage, mem['id'], photo())
    start(client, home)
    assert post(client, '/v1/reminders', home[2], reminder_body(home)).status_code == 201
    with engine.begin() as conn:
        conn.execute(text("UPDATE file_asset SET created_at=now()-interval '1 hour' WHERE id=:id"), {'id': file_id})
    async def copy_inventory():
        async with factory() as db:
            await service.note_possible_copy(db, UUID(home[3]), 'LLM:fictional.invalid')
            await db.commit()
    asyncio.run(copy_inventory())
    result, token = request_delete(client, home[4])
    assert client.get('/v1/me', headers=home[4]).status_code == 401
    assert client.get('/v1/me', headers=home[2]).status_code == 200
    assert client.get('/v1/memories/' + mem['id'], headers=home[2]).status_code == 404
    with engine.connect() as conn:
        for table in ('memory', 'conversation', 'reminder', 'consent', 'device_session', 'family_member'):
            column = {'memory': 'subject_user_id', 'conversation': 'owner_user_id', 'reminder': 'owner_user_id',
                'consent': 'subject_user_id', 'device_session': 'user_id', 'family_member': 'user_id'}[table]
            assert conn.execute(text(f'SELECT count(*) FROM {table} WHERE {column}=:uid'), {'uid': home[3]}).scalar() == 0
        assert conn.execute(text('SELECT display_name FROM "user" WHERE id=:uid'), {'uid': home[3]}).scalar() == '已删除账户'
        assert conn.execute(text('SELECT count(*) FROM family_member WHERE user_id=:uid'), {'uid': home[1]}).scalar() == 1
    storage.fail_delete = True
    assert asyncio.run(service.process_one(factory, storage, get_settings()))
    current = status(client, result, token).json()
    assert current['local_status'] == 'RETRY'
    assert current['status'] == 'PENDING' and current['last_error_code'] == 'STORAGE_DELETE_FAILED'
    assert storage.objects
    storage.fail_delete = False
    with engine.begin() as conn:
        conn.execute(text('UPDATE account_deletion SET retry_at=now()'))
    assert asyncio.run(service.process_one(factory, storage, get_settings()))
    assert not storage.objects
    current = status(client, result, token).json()
    assert current['local_status'] == 'ERASED' and current['status'] == 'PENDING'
    assert current['providers'] == [{'provider': 'LLM:fictional.invalid', 'status': 'REQUIRES_OPERATOR'}]
    async def confirm():
        async with factory() as db:
            await service.confirm_copy(db, UUID(result['id']), 'provider', 'fictional-verified-ticket', 'LLM:fictional.invalid')
            await service.confirm_copy(db, UUID(result['id']), 'backup', 'fictional-backup-inventory')
            await db.commit()
    asyncio.run(confirm())
    assert status(client, result, token).json()['status'] == 'COMPLETED'
    assert status(client, result, secrets.token_urlsafe(32)).status_code == 404
    assert client.post('/v1/account-deletions/lookup', json={'receipt_token': token}).json()['id'] == result['id']
    assert not asyncio.run(service.process_one(factory, storage, get_settings()))


def test_no_family_lost_response_and_explicit_self_confirmation(system):
    client, engine, factory, _ = system
    uid, headers = login(client, 'demo-other')
    assert client.post('/v1/me/deletion', headers=headers,
        json={'confirmation': 'yes', 'receipt_token': secrets.token_urlsafe(32)}).status_code == 422
    assert client.post('/v1/me/deletion', headers=headers, json={'confirmation': 'DELETE_MY_ACCOUNT',
        'receipt_token': secrets.token_urlsafe(32), 'user_id': 'someone-else'}).status_code == 422
    result, token = request_delete(client, headers)
    async def too_early():
        async with factory() as db:
            with pytest.raises(ValueError):
                await service.confirm_copy(db, UUID(result['id']), 'backup', 'not-yet')
    asyncio.run(too_early())
    assert asyncio.run(service.process_one(factory, None, get_settings()))
    assert status(client, result, token).json()['local_status'] == 'ERASED'
    assert status(client, result, token).json()['backup']['status'] == 'REQUIRES_OPERATOR'
    # A stale configured Demo identity cannot resurrect the erased account.
    response = client.post('/v1/auth/login', json={'credential': {'type': 'DEMO', 'identifier': 'demo-other'},
        'device': {'device_id': 'fictional', 'name': 'fictional', 'app_version': '0.1.0'}})
    assert response.status_code == 401


def test_live_upload_window_blocks_final_erasure(system):
    client, engine, factory, storage = system
    home = household(client)
    grant(client, home)
    mem = memory(client, home)
    upload(client, home, storage, mem['id'], photo())
    result, token = request_delete(client, home[4])
    asyncio.run(service.process_one(factory, storage, get_settings()))
    current = status(client, result, token).json()
    assert current['local_status'] == 'PENDING' and current['last_error_code'] == 'UPLOAD_WINDOW_OPEN'
    # Simulate a late signed PUT recreating raw bytes after account deletion.
    storage.objects[storage.keys[-1]] = b'late upload'
    with engine.begin() as conn:
        conn.execute(text("UPDATE file_asset SET created_at=now()-interval '1 hour'"))
        conn.execute(text('UPDATE account_deletion SET retry_at=now()'))
    asyncio.run(service.process_one(factory, storage, get_settings()))
    assert not storage.objects
    assert status(client, result, token).json()['local_status'] == 'ERASED'


def test_copy_inventory_survives_configuration_changes(system):
    client, _, factory, _ = system
    uid, headers = login(client, 'demo-other')
    async def copy():
        async with factory() as db:
            await service.note_possible_copy(db, UUID(uid), 'NOTIFICATION:twilio')
            await service.note_possible_copy(db, UUID(uid), 'NOTIFICATION:twilio')
            await db.commit()
    asyncio.run(copy())
    result, token = request_delete(client, headers)
    asyncio.run(service.process_one(factory, None, get_settings()))
    current = status(client, result, token).json()
    assert len(current['providers']) == 1 and current['status'] == 'PENDING'
    with pytest.raises(ValueError):
        async def unknown():
            async with factory() as db:
                await service.confirm_copy(db, UUID(result['id']), 'provider', 'fictional', 'not-used')
        asyncio.run(unknown())


def test_copy_deadline_is_not_proof_of_deletion(system):
    client, engine, factory, _ = system
    _, headers = login(client, 'demo-other')
    result, token = request_delete(client, headers)
    asyncio.run(service.process_one(factory, None, get_settings()))
    with engine.begin() as conn:
        conn.execute(text("UPDATE account_deletion SET backup_due_at=now()-interval '1 day'"))
    current = status(client, result, token).json()
    assert current['backup']['overdue'] and current['status'] == 'PENDING'


def test_related_notifications_messages_and_worker_results_are_removed(system):
    from backend.tests.integration.test_notifications import setup_event
    from backend.tests.integration.test_messages import register, body
    from app.worker.tasks import run_one
    client, engine, factory, storage = system
    home, _, _, _ = setup_event(system)
    grant(client, home)
    mem = memory(client, home)
    register(client, home[2], home[0])
    register(client, home[4], home[0], True)
    sent = post(client, '/v1/messages', home[4], body(home[0], 'CHILD', 'fictional-erased-message'))
    assert sent.status_code == 201
    # Persist an example external reference without making any provider call.
    with engine.begin() as conn:
        conn.execute(text("UPDATE notification SET provider='twilio', channel='SMS'"))
        conn.execute(text("""INSERT INTO notification_attempt (id, notification_id, attempt_no, provider, status, provider_message_id)
            SELECT id, id, 1, 'twilio', 'SUCCEEDED', 'fictional-provider-resource' FROM notification"""))
    result, token = request_delete(client, home[4])
    async def drain():
        for _ in range(10):
            if not await run_one(factory, storage):
                break
    asyncio.run(drain())
    asyncio.run(service.process_one(factory, storage, get_settings()))
    with engine.connect() as conn:
        for table in ('signal_event', 'notification', 'notification_attempt', 'family_message', 'message_delivery', 'memory', 'memory_chunk', 'memory_embedding'):
            assert conn.execute(text(f'SELECT count(*) FROM {table}')).scalar() == 0
        refs = conn.execute(text('SELECT resource_refs FROM provider_copy')).scalar()
        assert refs[0]['resource_id'] == 'fictional-provider-resource'
        assert conn.execute(text('SELECT count(*) FROM task_outbox WHERE resource_id=:id'), {'id': mem['id']}).scalar() == 0
    assert 'fictional-provider-resource' not in status(client, result, token).text


def test_deleting_contributor_preserves_other_subject_content_and_rejects_token_collision(system):
    client, engine, factory, storage = system
    home = household(client)
    grant(client, home)
    mem = memory(client, home)
    reminder = post(client, '/v1/reminders', home[2], reminder_body(home)).json()
    result, token = request_delete(client, home[2])
    asyncio.run(service.process_one(factory, storage, get_settings()))
    assert client.get('/v1/memories/' + mem['id'], headers=home[4]).status_code == 200
    assert client.get('/v1/reminders/' + reminder['id'], headers=home[4]).status_code == 200
    assert client.get('/v1/me', headers=home[4]).status_code == 200
    collision = client.post('/v1/me/deletion', headers=home[4], json={
        'confirmation': 'DELETE_MY_ACCOUNT', 'receipt_token': token})
    assert collision.status_code == 409
    assert client.get('/v1/me', headers=home[4]).status_code == 200


def test_export_failure_never_returns_partial_zip(system, monkeypatch):
    from app.platform.errors import AppError
    client, _, _, storage = system
    home = household(client)
    grant(client, home)
    mem = memory(client, home)
    upload(client, home, storage, mem['id'], photo())
    async def unavailable(*_):
        raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', 'Unavailable', 503)
    monkeypatch.setattr(storage, 'read', unavailable)
    response = client.get('/v1/me/export', headers=home[4])
    assert response.status_code == 503 and response.headers['content-type'].startswith('application/json')


def test_inflight_provider_send_blocks_completion_but_not_account_lockout(system):
    client, _, factory, _ = system
    uid, headers = login(client, 'demo-other')
    async def run():
        async with factory() as gate:
            await service.send_gate(gate, UUID(uid), shared=True)
            result, token = await asyncio.to_thread(request_delete, client, headers)
            worker = asyncio.create_task(service.process_one(factory, None, get_settings()))
            try:
                await asyncio.sleep(0.1)
                assert not worker.done()
                assert (await asyncio.to_thread(client.get, '/v1/me', headers=headers)).status_code == 401
            finally:
                await gate.rollback()
                await worker
            assert (await asyncio.to_thread(status, client, result, token)).json()['local_status'] == 'ERASED'
    asyncio.run(run())


def test_retention_keeps_unfinished_work_and_live_upload_cleanup_marker(system):
    client, engine, factory, storage = system
    home = household(client)
    grant(client, home)
    mem = memory(client, home)
    file_id, _ = upload(client, home, storage, mem['id'], photo())
    with engine.begin() as conn:
        conn.execute(text("UPDATE audit_log SET created_at=now()-interval '100 days'"))
        conn.execute(text("UPDATE audit_log SET action='FILE_UPLOAD_WINDOW_CLOSED' WHERE target_id=:id AND action='FILE_CONFIRMED'"), {'id': file_id})
        conn.execute(text("UPDATE task_outbox SET status=CASE WHEN kind='MEMORY_INDEX' THEN 'DEAD' ELSE 'SUCCEEDED' END, updated_at=now()-interval '10 days'"))
    async def sweep():
        async with factory() as db:
            await service.maintenance(db, get_settings())
            await db.commit()
    asyncio.run(sweep())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT action FROM audit_log')).scalars().all() == ['FILE_UPLOAD_WINDOW_CLOSED']
        assert conn.execute(text('SELECT status FROM task_outbox')).scalars().all() == ['DEAD']
