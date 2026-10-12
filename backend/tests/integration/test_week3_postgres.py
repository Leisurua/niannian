"""Real PostgreSQL Week 3 API/worker/WSS tests; object bytes use labelled Mock storage.

Only the explicitly configured *_week3_test database is ever truncated.
"""
import asyncio
from datetime import timedelta
import hashlib
from io import BytesIO
import os
import re
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.modules.auth.api import _attempts
from app.modules.memory.files import cleanup
from app.modules.reminder.service import tick
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow

URL = os.environ.get('WEEK3_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Set an explicitly disposable WEEK3_TEST_DATABASE_URL')


class MockObjectStorage:
    provider = 'mock'

    def __init__(self):
        self.objects = {}
        self.keys = []
        self.fail_delete = False

    async def upload_url(self, key, mime, size, seconds):
        self.keys.append(key)
        return 'https://mock.invalid/upload'

    async def read(self, key, maximum):
        if key not in self.objects:
            raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', 'Mock object missing', 503)
        data = self.objects[key]
        if len(data) > maximum:
            raise AppError('FILE_TOO_LARGE', 'Mock object too large', 413)
        return data

    async def write(self, key, data, mime):
        self.objects[key] = data

    async def delete(self, key):
        if self.fail_delete:
            raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', 'Mock deletion failure', 503)
        self.objects.pop(key, None)


@pytest.fixture
def system(monkeypatch):
    parsed = make_url(URL)
    if parsed.drivername != 'postgresql+psycopg' or parsed.query or not re.fullmatch(r'[A-Za-z0-9_]+_week3_test', parsed.database or ''):
        pytest.fail('Refusing a non-disposable database or connection overrides')
    monkeypatch.setenv('AUTH_SIGNING_KEY', 'fictional-week3-signing-key-' * 3)
    monkeypatch.setenv('AUTH_LOGIN_LIMIT', '1000')
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('PROVIDER_MODE', 'mock')
    get_settings.cache_clear()
    _attempts.clear()
    engine = create_engine(URL)
    with engine.begin() as conn:
        conn.execute(text('TRUNCATE "user" CASCADE'))
    async_engine = create_async_engine(URL, poolclass=NullPool)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    app.state.session_factory = factory
    storage = MockObjectStorage()
    app.state.object_storage = storage
    with TestClient(app) as client:
        yield client, engine, factory, storage
    del app.state.session_factory
    del app.state.object_storage
    asyncio.run(async_engine.dispose())
    engine.dispose()
    get_settings.cache_clear()


def login(client, name):
    response = client.post('/v1/auth/login', json={'credential': {'type': 'DEMO', 'identifier': name},
        'device': {'device_id': str(uuid4()), 'name': 'fictional device', 'app_version': '0.1.0'}})
    assert response.status_code == 201, response.text
    result = response.json()
    return result['user']['id'], {'Authorization': 'Bearer ' + result['access_token']}


def post(client, path, headers, body=None, key=None):
    return client.post(path, headers={**headers, 'Idempotency-Key': key or str(uuid4())}, json=body if body is not None else {})


def household(client, child_name='demo-child'):
    child, ch = login(client, child_name)
    elder, eh = login(client, 'demo-elder')
    family = post(client, '/v1/families', ch, {'name': '虚构测试家庭'}).json()['id']
    invite = post(client, f'/v1/families/{family}/invitations', ch,
        {'target_role': 'ELDER', 'expires_at': (utcnow() + timedelta(hours=1)).isoformat()}).json()['token']
    assert post(client, f'/v1/family-invitations/{invite}/accept', eh, {'confirm_identity': True}).status_code == 200
    return family, child, ch, elder, eh


def grant(client, home, scope='FAMILY_MEMORY'):
    fid, child, ch, elder, eh = home
    result = post(client, '/v1/consents', eh, dict(family_id=fid, subject_user_id=elder, grantee_user_id=child, scope=scope, source='SETTINGS'))
    assert result.status_code == 201, result.text
    return result.json()['id']


def memory(client, home, **changes):
    fid, child, ch, elder, eh = home
    result = post(client, '/v1/memories', ch, dict(family_id=fid, subject_user_id=elder, type='EVENT', title='虚构往事', content='仅用于验证',
        required_consent_scope='FAMILY_MEMORY', verification_status='CONFIRMED') | changes)
    assert result.status_code == 201, result.text
    return result.json()


def test_memory_authorization_candidate_confirmation_version_and_revocation(system):
    client, engine, _, _ = system
    home = household(client)
    fid, child, ch, elder, eh = home
    body = dict(family_id=fid, subject_user_id=elder, type='EVENT', title='候选', content='虚构', required_consent_scope='FAMILY_MEMORY')
    assert post(client, '/v1/memories', ch, body).status_code == 403
    consent_id = grant(client, home)
    assert post(client, '/v1/memories', ch, body | {'source': 'AI_CANDIDATE', 'verification_status': 'CONFIRMED'}).status_code == 422
    draft = post(client, '/v1/memories', ch, body | {'source': 'AI_CANDIDATE'}, key='candidate-once').json()
    assert post(client, '/v1/memories', ch, body | {'source': 'AI_CANDIDATE'}, key='candidate-once').json()['id'] == draft['id']
    assert post(client, '/v1/memories', ch, body | {'title': '另一候选'}, key='candidate-once').status_code == 409
    path = '/v1/memories/' + draft['id']
    assert client.get('/v1/memories', headers=eh).json()['items'] == []
    assert client.get('/v1/memories?pending_confirmation=true', headers=ch).json()['items'][0]['id'] == draft['id']
    confirmed = post(client, path + '/confirm', ch, key='confirm-once').json()
    assert confirmed['verification_status'] == 'CONFIRMED'
    assert post(client, path + '/confirm', ch, key='confirm-once').json()['version'] == confirmed['version']
    assert len(client.get('/v1/memories', headers=eh).json()['items']) == 1
    assert client.patch(path, headers={**ch, 'If-Match': '1'}, json={'title': '已过期更新'}).status_code == 409
    edited = client.patch(path, headers={**ch, 'If-Match': str(confirmed['version'])}, json={'content': '修改后须再次确认'}).json()
    assert edited['verification_status'] == 'PENDING'
    assert post(client, path + '/confirm', ch).status_code == 200
    outsider, oh = login(client, 'demo-other')
    assert client.get(path, headers=oh).status_code == 404
    assert post(client, '/v1/consents/' + consent_id + '/revoke', eh).status_code == 201
    assert client.get(path, headers=ch).status_code == 404
    assert client.get('/v1/memories', headers=ch).json()['items'] == []
    # Data subject can still delete without granting fresh family read consent.
    deleted = client.delete(path, headers={**eh, 'Idempotency-Key': 'delete-once'})
    assert deleted.status_code == 202
    assert client.delete(path, headers={**eh, 'Idempotency-Key': 'delete-once'}).json() == deleted.json()
    assert client.get(path, headers=eh).status_code == 404
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_log WHERE action='MEMORY_DELETE'")).scalar() == 1


def test_scope_filters_owner_only_expiry_and_cross_family_pagination(system):
    client, engine, _, _ = system
    home = household(client)
    grant(client, home)
    first = memory(client, home)
    fid, child, ch, elder, eh = home
    private = post(client, '/v1/memories', eh, dict(family_id=fid, subject_user_id=elder, type='EVENT', title='仅本人',
        content='虚构', required_consent_scope='FAMILY_MEMORY', visibility='OWNER_ONLY', verification_status='CONFIRMED')).json()
    assert client.get('/v1/memories/' + private['id'], headers=ch).status_code == 404
    for _ in range(3): memory(client, home)
    one = client.get('/v1/memories?limit=2', headers=ch).json()
    two = client.get('/v1/memories?limit=2&cursor=' + one['page']['next_cursor'], headers=ch).json()
    assert len(one['items']) == len(two['items']) == 2
    assert not set(i['id'] for i in one['items']) & set(i['id'] for i in two['items'])
    home2 = household(client, 'demo-other')
    grant(client, home2)
    assert client.get('/v1/memories/' + first['id'], headers=home2[2]).status_code == 404
    assert client.get('/v1/memories?family_id=' + fid, headers=home2[2]).json()['items'] == []
    with engine.begin() as conn:
        conn.execute(text('UPDATE memory SET expires_at=:past WHERE id=:id'), {'past': utcnow()-timedelta(seconds=1), 'id': UUID(first['id'])})
    assert client.get('/v1/memories/' + first['id'], headers=eh).status_code == 404


def photo():
    output = BytesIO()
    metadata = PngInfo(); metadata.add_text('Comment', 'fictional location metadata')
    Image.new('RGB', (4, 4), 'blue').save(output, format='PNG', pnginfo=metadata)
    return output.getvalue()


def upload(client, home, storage, memory_id, data):
    checksum = hashlib.sha256(data).hexdigest()
    result = post(client, '/v1/files/upload-requests', home[2], dict(memory_id=memory_id, media_type='PHOTO', mime_type='image/png', size_bytes=len(data), checksum=checksum))
    assert result.status_code == 201, result.text
    storage.objects[storage.keys[-1]] = data
    fid = result.json()['file']['id']
    result = post(client, '/v1/files/' + fid + '/confirm', home[2], {'checksum': checksum}, key='confirm-'+fid)
    assert result.status_code == 202, result.text
    return fid, result.json()


def test_file_decode_metadata_strip_signed_proxy_revoke_and_cleanup(system):
    client, engine, factory, storage = system
    home = household(client); cid = grant(client, home)
    item = memory(client, home)
    fid, result = upload(client, home, storage, item['id'], photo())
    assert result['status'] == 'AVAILABLE'
    signed = client.get('/v1/files/' + fid + '/download-url', headers=home[2]).json()['download_url']
    url = urlsplit(signed); path = url.path + '?' + url.query
    fetched = client.get(path, headers=home[2])
    assert fetched.status_code == 200
    assert fetched.headers['cache-control'] == 'no-store'
    with Image.open(BytesIO(fetched.content)) as image:
        assert not image.info and image.size == (4, 4)
    # Reusing a still-valid upload URL cannot overwrite the clean object.
    storage.objects[storage.keys[-1]] = b'<script>fictional hostile replacement</script>'
    assert client.get(path, headers=home[2]).content == fetched.content
    assert client.get(path).status_code == 401
    assert client.get(path, headers=home[4]).status_code == 404  # signer is bound to child
    assert post(client, '/v1/consents/' + cid + '/revoke', home[4]).status_code == 201
    assert client.get(path, headers=home[2]).status_code == 404
    deletion = client.delete('/v1/memories/' + item['id'], headers={**home[4], 'Idempotency-Key': 'erase-memory'})
    assert deletion.status_code == 202
    async def clean():
        async with factory() as db:
            await cleanup(db, storage)
            await db.commit()
    storage.fail_delete = True
    asyncio.run(clean())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM file_asset WHERE id=:id'), {'id': UUID(fid)}).scalar() == 'DELETE_REQUESTED'
    storage.fail_delete = False
    asyncio.run(clean())
    assert storage.objects == {}
    assert client.get(path, headers=home[2]).status_code == 404


def test_file_quarantine_wrong_checksum_and_no_unscoped_upload(system):
    client, _, _, storage = system
    home = household(client); grant(client, home)
    item = memory(client, home)
    data = b'\x89PNG\r\n\x1a\nnot a decoded image'
    fid, result = upload(client, home, storage, item['id'], data)
    assert result['status'] == 'QUARANTINED'
    assert client.get('/v1/files/' + fid + '/download-url', headers=home[2]).status_code == 404
    assert post(client, '/v1/files/upload-requests', home[2], dict(media_type='PHOTO', mime_type='image/png', size_bytes=5, checksum='a'*64)).status_code == 422


def reminder_body(home, **changes):
    due = utcnow() + timedelta(minutes=2)
    return dict(family_id=home[0], owner_user_id=home[3], type='WATER', title='喝水提醒', content='虚构提醒',
        schedule_time_local=due.strftime('%H:%M:%S'), timezone='UTC', start_date=due.date().isoformat(), recurrence_kind='DAILY') | changes


def test_reminder_occurrence_feedback_later_and_no_response(system):
    client, engine, factory, _ = system
    home = household(client)
    created = post(client, '/v1/reminders', home[2], reminder_body(home)).json()
    assert 'id' in created, created
    from datetime import datetime
    due = datetime.fromisoformat(created['next_due_at'])
    async def run(now):
        async with factory() as db:
            await tick(db, get_settings(), now)
            await db.commit()
    asyncio.run(run(due)); asyncio.run(run(due))
    executions = client.get(f"/v1/reminders/{created['id']}/executions", headers=home[2]).json()['items']
    assert len(executions) == 1 and executions[0]['feedback_status'] == 'PENDING'
    eid = executions[0]['id']
    assert post(client, '/v1/reminder-executions/'+eid+'/feedback', home[2], {'status':'DONE'}).status_code == 404
    assert post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'NO_RESPONSE'}).status_code == 422
    later = utcnow() + timedelta(minutes=10)
    result = post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'LATER','next_due_at':later.isoformat()}, key='later-once')
    assert result.status_code == 200
    asyncio.run(run(later + timedelta(seconds=1)))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM reminder_execution')).scalar() == 1
    asyncio.run(run(later + timedelta(hours=2)))
    assert client.get(f"/v1/reminders/{created['id']}/executions", headers=home[2]).json()['items'][0]['feedback_status'] == 'NO_RESPONSE'
    done = post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'DONE'}, key='done-once')
    assert done.status_code == 200
    assert post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'DONE'}, key='done-once').json() == done.json()


def test_reminder_medication_consent_family_selection_and_version(system):
    client, _, _, _ = system
    home = household(client)
    body = reminder_body(home, type='MEDICATION')
    assert post(client, '/v1/reminders', home[2], body).status_code == 403
    assert post(client, '/v1/reminders', home[4], body).status_code == 403
    cid = grant(client, home, 'HEALTH_MEDICATION')
    item = post(client, '/v1/reminders', home[2], body).json()
    changed = client.patch('/v1/reminders/'+item['id'], headers={**home[2],'If-Match':'1'}, json=body|{'title':'新提醒'})
    assert changed.status_code == 200
    assert client.patch('/v1/reminders/'+item['id'], headers={**home[2],'If-Match':'1'}, json=body).status_code == 409
    post(client, '/v1/consents/'+cid+'/revoke', home[4])
    assert client.get('/v1/reminders/'+item['id'], headers=home[2]).status_code == 404
    household(client, 'demo-other')
    no_family = reminder_body(home); no_family.pop('family_id')
    assert post(client, '/v1/reminders', home[4], no_family).status_code == 422


def ws_frame(cid, kind, sequence, payload=None):
    return dict(type=kind, conversation_id=cid, sequence=sequence, occurred_at=utcnow().isoformat(), payload=payload or {})


def test_wss_owner_identity_reconnect_replay_and_end(system):
    client, engine, _, _ = system
    home = household(client)
    cid = post(client, '/v1/conversations', home[4], {'family_id': home[0], 'input_mode':'TEXT'}).json()['id']
    path = '/v1/ws/conversations/' + cid
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers=home[2]): pass
    with client.websocket_connect(path, headers=home[4]) as ws:
        ready = ws.receive_json(); assert ready['type'] == 'session.ready'
        ws.send_json(ws_frame(cid, 'session.start', 1, {'client_session_id':'fictional-client', 'input_mode':'TEXT'}))
        assert ws.receive_json()['type'] == 'session.ready'
        identity = ws.receive_json(); assert 'Mock' in identity['payload']['text']
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text':'虚构输入不应持久化'}))
        assert ws.receive_json()['type'] == 'error'
        last = ws.receive_json()['sequence']
    with client.websocket_connect(path, headers=home[4]) as ws:
        assert ws.receive_json()['sequence'] > last
        ws.send_json(ws_frame(cid, 'session.start', 3, {'client_session_id':'fictional-client', 'input_mode':'TEXT'}))
        assert ws.receive_json()['type'] == 'session.ready'
        ws.send_json(ws_frame(cid, 'ping', 4))
        assert ws.receive_json()['type'] == 'pong'  # no repeated identity message
        ws.send_json(ws_frame(cid, 'ping', 4))
        assert ws.receive_json()['payload']['code'] == 'WS_SEQUENCE_REPLAY'
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'session.end', 5, {'reason':'USER'}))
        assert ws.receive_json()['payload']['state'] == 'IDLE'
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers=home[4]): pass
    assert client.get('/v1/conversations/'+cid, headers=home[4]).json()['status'] == 'COMPLETED'
    with engine.connect() as conn:
        assert '虚构输入不应持久化' not in str(conn.execute(text('SELECT provider_metadata,summary_text FROM conversation')).all())


def test_wss_revoked_login_closes_live_connection_and_audio_is_disabled(system):
    client, _, _, _ = system
    home = household(client)
    assert post(client, '/v1/conversations', home[4], {'family_id':home[0], 'input_mode':'VOICE'}).status_code == 503
    cid = post(client, '/v1/conversations', home[4], {'family_id':home[0], 'input_mode':'TEXT'}).json()['id']
    path = '/v1/ws/conversations/'+cid
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        assert post(client, '/v1/auth/logout', home[4]).status_code == 204
        ws.send_json(ws_frame(cid,'ping',1))
        with pytest.raises(WebSocketDisconnect): ws.receive_json()


def test_memory_id_enumeration_errors_are_identical(system):
    client, _, _, _ = system
    home = household(client); grant(client, home)
    item = memory(client, home)
    _, outsider = login(client, 'demo-other')
    known = client.get('/v1/memories/'+item['id'], headers=outsider)
    unknown = client.get('/v1/memories/'+str(uuid4()), headers=outsider)
    assert known.status_code == unknown.status_code == 404
    assert known.json()['error'] == unknown.json()['error']


def test_concurrent_same_key_creation_and_worker_tick_are_unique(system):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    client, engine, factory, _ = system
    home = household(client); grant(client, home)
    body = dict(family_id=home[0], subject_user_id=home[3], type='EVENT', title='并发虚构候选',
                content='虚构', required_consent_scope='FAMILY_MEMORY')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(client, '/v1/memories', home[2], body, key='parallel-create'), range(2)))
    assert all(r.status_code == 201 for r in responses)
    assert responses[0].json()['id'] == responses[1].json()['id']
    item = post(client, '/v1/reminders', home[2], reminder_body(home)).json()
    due = datetime.fromisoformat(item['next_due_at'])
    async def run():
        async with factory() as db:
            await tick(db, get_settings(), due)
            await db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: asyncio.run(run()), range(2)))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM reminder_execution')).scalar() == 1


def test_late_signed_put_raw_object_is_reclaimed_after_upload_window(system):
    client, _, factory, storage = system
    home = household(client); grant(client, home)
    item = memory(client, home)
    upload(client, home, storage, item['id'], photo())
    key = storage.keys[-1]
    storage.objects[key] = b'fictional replay'
    async def run():
        async with factory() as db:
            await cleanup(db, storage, utcnow()+timedelta(minutes=7))
            await db.commit()
    asyncio.run(run())
    assert key not in storage.objects and key+'.safe' in storage.objects


def test_wss_malformed_audio_family_loss_and_parallel_connections(system):
    client, _, _, _ = system
    home = household(client)
    assert post(client, '/v1/conversations', home[2], {'family_id':home[0], 'input_mode':'TEXT'}).status_code == 403
    cid = post(client, '/v1/conversations', home[4], {'family_id':home[0], 'input_mode':'TEXT'}).json()['id']
    path = '/v1/ws/conversations/'+cid
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path, headers=home[4]): pass
        ws.send_text('{invalid')
        assert ws.receive_json()['payload']['code'] == 'WS_INVALID_MESSAGE'
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'audio.chunk', 1, {'base64_data':'fictional'}))
        assert ws.receive_json()['payload']['code'] == 'WS_AUDIO_DISABLED'
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        members = client.get('/v1/families/'+home[0]+'/members', headers=home[2]).json()['items']
        elder = next(m for m in members if m['user_id'] == home[3])
        result = client.patch('/v1/families/'+home[0]+'/members/'+elder['id'],
            headers={**home[2], 'If-Match':str(elder['version'])}, json={'status':'REVOKED'})
        assert result.status_code == 200
        ws.send_json(ws_frame(cid, 'ping', 1))
        with pytest.raises(WebSocketDisconnect): ws.receive_json()
