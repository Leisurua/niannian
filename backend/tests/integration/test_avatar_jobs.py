import asyncio
from io import BytesIO
import hashlib
from uuid import UUID
from zipfile import ZipFile

from PIL import Image
import pytest
from sqlalchemy import text

from app.integrations.tha3_renderer import write_pack
from app.modules.avatar import api, service, worker
from app.platform.config import get_settings
from backend.tests.support import URL, household, login, photo, post

pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable TEST_DATABASE_URL required')


@pytest.fixture
def config(system, monkeypatch):
    settings = get_settings().model_copy(update=dict(app_env='dev', avatar_generation_enabled=True,
        avatar_image_provider='qwen', avatar_image_base_url='https://example.invalid/api/v1',
        avatar_image_model='fictional-editor', avatar_image_api_key='fictional-key',
        avatar_tha3_python='unused', avatar_tha3_root='unused', avatar_tha3_models='unused',
        avatar_face_cascade='unused', avatar_rembg_models='unused'))
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    return settings


def setup_job(system, config):
    client, _, _, storage = system
    home = household(client)
    grant = post(client, '/v1/consents', home[4], dict(family_id=home[0], subject_user_id=home[3],
        grantee_user_id=home[3], scope='PORTRAIT', source='SETTINGS'))
    assert grant.status_code == 201
    caps = client.get('/v1/avatar-generation', headers=home[4]).json()
    raw = photo()
    body = dict(family_id=home[0], consent_id=grant.json()['id'], provider_id=caps['provider_id'],
        authorized_photo=True, mime_type='image/png', size_bytes=len(raw), checksum=hashlib.sha256(raw).hexdigest())
    created = post(client, '/v1/avatar-jobs', home[4], body, key='create-once')
    assert created.status_code == 201, created.text
    assert post(client, '/v1/avatar-jobs', home[4], body, key='create-once').json()['id'] == created.json()['id']
    storage.objects[storage.keys[-1]] = raw
    path = '/v1/avatar-jobs/' + created.json()['id']
    complete = post(client, path + '/complete-upload', home[4], key='upload-once')
    assert complete.status_code == 200, complete.text
    assert complete.json()['status'] == 'QUEUED'
    assert post(client, path + '/complete-upload', home[4], key='upload-once').status_code == 200
    return home, path, grant.json()['id']


class Editor:
    def __init__(self, hook=None): self.calls = 0; self.hook = hook
    async def edit(self, photo, mime):
        self.calls += 1
        if self.hook: self.hook()
        return b'fictional-illustration'


class Renderer:
    def __init__(self, hook=None): self.calls = 0; self.hook = hook
    async def prepare(self, illustration): return illustration
    async def render(self, illustration):
        self.calls += 1
        if self.hook: self.hook()
        frame = Image.new('RGBA', (512, 512)); frame.paste((255, 160, 20, 255), (180, 60, 330, 500))
        stream = BytesIO(); write_pack(stream, lambda _: frame, 'Synthetic integration fixture')
        return stream.getvalue(), b''


def run(system, config, editor=None, renderer=None):
    _, _, factory, storage = system
    assert asyncio.run(worker.run_one(factory, storage, config, editor=editor or Editor(), renderer=renderer or Renderer()))


def test_photo_job_only_activates_after_explicit_preview_confirmation(system, config):
    client, engine, _, _ = system
    home, path, _ = setup_job(system, config)
    assert client.get(path + '/pack', headers=home[4]).status_code == 409
    run(system, config)
    ready = client.get(path, headers=home[4]).json()
    assert ready['status'] == 'READY' and ready['confirmed_at'] is None
    pack = client.get(path + '/pack', headers=home[4])
    assert pack.status_code == 200 and pack.headers['cache-control'] == 'no-store'
    assert hashlib.sha256(pack.content).hexdigest() == ready['pack_checksum']
    assert client.get(path + '/preview', headers=home[4]).headers['content-type'] == 'image/png'
    assert client.get(path, headers=home[2]).status_code == 404
    _, outsider = login(client, 'demo-other')
    assert client.get(path + '/pack', headers=outsider).status_code == 404
    assert post(client, path + '/confirm', home[4], {'pack_checksum': '0' * 64}).status_code == 409
    body = {'pack_checksum': ready['pack_checksum']}
    active = post(client, path + '/confirm', home[4], body, key='confirm-once')
    assert active.status_code == 200 and active.json()['status'] == 'ACTIVE'
    assert post(client, path + '/confirm', home[4], body, key='confirm-once').json()['confirmed_at'] == active.json()['confirmed_at']
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM task_outbox WHERE kind='AVATAR_GENERATE'")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM provider_copy WHERE provider LIKE 'IMAGE:%'")).scalar() == 1


@pytest.mark.parametrize('stage', ['edit', 'render'])
def test_revocation_during_generation_never_publishes_late_result(system, config, stage):
    client, engine, _, storage = system
    home, path, consent_id = setup_job(system, config)
    def revoke():
        assert post(client, '/v1/consents/' + consent_id + '/revoke', home[4]).status_code == 201
    run(system, config, editor=Editor(revoke if stage == 'edit' else None), renderer=Renderer(revoke if stage == 'render' else None))
    assert client.get(path + '/pack', headers=home[4]).status_code in (403, 404)
    assert not any('/pack.safe' in key for key in storage.objects)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM avatar_job')).scalar() == 'CANCELLED'


def test_provider_change_and_invalid_upload_fail_closed(system, config, monkeypatch):
    client, engine, _, _ = system
    home, path, _ = setup_job(system, config)
    editor = Editor()
    run(system, config.model_copy(update={'avatar_image_model': 'another-provider-model'}), editor=editor)
    assert editor.calls == 0
    assert client.get(path, headers=home[4]).json()['status'] == 'FAILED'
    assert client.delete(path, headers=home[4]).status_code == 202
    assert client.delete(path, headers=home[4]).status_code == 202


def test_expired_worker_lease_does_not_resend_photo(system, config):
    client, engine, factory, storage = system
    home, path, _ = setup_job(system, config)
    with engine.begin() as conn:
        conn.execute(text("UPDATE task_outbox SET status='RUNNING', attempts=1, lease_token=id, lease_until=now()-interval '1 second' WHERE kind='AVATAR_GENERATE'"))
    editor = Editor()
    assert not asyncio.run(worker.run_one(factory, storage, config, editor=editor, renderer=Renderer()))
    async def maintain():
        async with factory() as db:
            await service.maintenance(db); await db.commit()
    asyncio.run(maintain())
    assert editor.calls == 0
    assert client.get(path, headers=home[4]).json()['error_code'] == 'WORKER_INTERRUPTED'


def test_avatar_export_and_account_erasure_cover_private_assets(system, config):
    from backend.tests.integration.test_account_lifecycle import request_delete
    from app.modules.account import service as accounts
    client, engine, factory, storage = system
    home, path, _ = setup_job(system, config); run(system, config)
    export = client.get('/v1/me/export', headers=home[4])
    assert export.status_code == 200
    with ZipFile(BytesIO(export.content)) as archive:
        assert any(name.endswith('/pack.zip') for name in archive.namelist())
    receipt, _ = request_delete(client, home[4])
    assert client.get(path, headers=home[4]).status_code == 401
    with engine.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM avatar_job')).scalar() == 0
        conn.execute(text("UPDATE file_asset SET created_at=now()-interval '1 hour'"))
    assert asyncio.run(accounts.process_one(factory, storage, config))
    assert storage.objects == {}
