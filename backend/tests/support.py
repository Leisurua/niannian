import asyncio
import hashlib
import os
import re
import threading
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from app.ai.conversation import MockConversationLLM
from app.main import app
from app.modules.auth.api import _attempts
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow
from fastapi.testclient import TestClient
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

KEY = 'fictional-test-signing-key-' * 3
URL = os.environ.get('TEST_DATABASE_URL')

def require_test_database(url):
    try:
        parsed = make_url(url)
    except Exception as exc:
        raise ValueError('Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test') from exc
    if parsed.drivername != 'postgresql+psycopg' or parsed.query or not re.fullmatch(r'[A-Za-z0-9_]+_test', parsed.database or ''):
        raise ValueError('Refusing to reset a database without a safe _test name or with connection overrides')
    return parsed

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
    require_test_database(URL)
    monkeypatch.setenv('AUTH_SIGNING_KEY', KEY)
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


def reminder_body(home, **changes):
    due = utcnow() + timedelta(minutes=2)
    return dict(family_id=home[0], owner_user_id=home[3], type='WATER', title='喝水提醒', content='虚构提醒',
        schedule_time_local=due.strftime('%H:%M:%S'), timezone='UTC', start_date=due.date().isoformat(), recurrence_kind='DAILY') | changes


def ws_frame(cid, kind, sequence, payload=None):
    return dict(type=kind, conversation_id=cid, sequence=sequence, occurred_at=utcnow().isoformat(), payload=payload or {})


def start(client, home):
    return post(client, '/v1/conversations', home[4], {'family_id': home[0], 'input_mode': 'TEXT'}).json()['id']


def handshake(ws, cid):
    assert ws.receive_json()['type'] == 'session.ready'
    ws.send_json(ws_frame(cid, 'session.start', 1, {'client_session_id': 'fictional', 'input_mode': 'TEXT'}))
    assert ws.receive_json()['type'] == 'session.ready'
    assert '我是念念 AI' in ws.receive_json()['payload']['text']


class HeldLLM(MockConversationLLM):
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()

    async def generate(self, request):
        self.started.set()
        try:
            while not self.release.is_set():
                await asyncio.sleep(0.01)
            return await super().generate(request)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
