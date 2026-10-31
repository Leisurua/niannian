import asyncio
from io import BytesIO
import wave

import pytest
from app.main import app
from app.modules.voice import worker
from app.platform.config import get_settings
from backend.tests.support import URL, household, post, start, ws_frame

pytestmark = pytest.mark.skipif(not URL, reason='Disposable PostgreSQL required')


class Provider:
    async def create(self, sample, prefix):
        return 'cosyvoice-v3.5-flash-' + prefix

    async def query(self, voice_id):
        return 'OK'

    async def stream(self, text, voice_id, speed=1.0):
        yield b'\0\0' * 2400

    async def delete(self, voice_id):
        pass


def sample():
    result = BytesIO()
    with wave.open(result, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\0\0' * 240000)
    return result.getvalue()


def test_owner_approval_publication_cloud_stream_and_revoke(system, monkeypatch):
    client, _, factory, storage = system
    home = household(client)
    monkeypatch.setenv('APP_ENV', 'dev')
    monkeypatch.setenv('FAMILY_VOICE_ENABLED', 'true')
    monkeypatch.setenv('FAMILY_VOICE_WORKSPACE_ID', 'fictional')
    monkeypatch.setenv('FAMILY_VOICE_API_KEY', 'fictional')
    get_settings.cache_clear()
    created = post(client, '/v1/voice-profiles', home[2], dict(family_id=home[0],
        owner_user_id=home[1], display_name='测试家属')).json()
    profile = created['id']
    path = '/v1/voice-profiles/' + profile
    assert client.put(path + '/sample', headers=home[2], content=sample()).status_code == 200
    assert post(client, path + '/approve', home[4]).status_code == 403
    assert post(client, path + '/approve', home[2]).status_code == 200
    assert client.get('/v1/voice-profiles', headers=home[4], params={'family_id': home[0], 'available': True}).json()['items'] == []
    assert asyncio.run(worker.run_one(factory, storage, get_settings(), provider=Provider()))
    assert client.get(path, headers=home[2]).json()['status'] == 'READY'
    assert client.get(path + '/sample', headers=home[2]).status_code == 404
    assert post(client, path + '/activate', home[2]).json()['status'] == 'ACTIVE'
    assert client.put('/v1/voice-preferences', headers=home[4], json=dict(family_id=home[0],
        voice_profile_id=profile, cloud_tts_allowed=True)).status_code == 200
    assert post(client, '/v1/consents', home[4], dict(family_id=home[0], subject_user_id=home[3],
        grantee_user_id=home[3], scope='VOICE', source='SETTINGS')).status_code == 201
    cid = start(client, home)
    app.state.family_voice_provider = Provider()
    try:
        with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
            previous = ws.receive_json()['sequence']
            ws.send_json(ws_frame(cid, 'session.start', 1, dict(client_session_id='test', input_mode='TEXT', audio_capabilities=['pcm_v1'])))
            seen = []
            while 'tts.end' not in seen:
                event = ws.receive_json()
                assert event['sequence'] == previous + 1
                previous = event['sequence']
                seen.append(event['type'])
                if event['type'] == 'assistant.text':
                    assert event['payload']['speech_mode'] == 'cloud'
            assert 'tts.chunk' in seen
            assert client.delete(path, headers=home[2]).status_code == 202
            event = ws.receive_json()
            assert event['type'] == 'tts.error'
        assert asyncio.run(worker.run_one(factory, storage, get_settings(), provider=Provider()))
        assert client.get(path, headers=home[2]).json()['status'] == 'DELETED'
    finally:
        del app.state.family_voice_provider
        get_settings.cache_clear()


def test_unapproved_expired_sample_cleanup_without_cloud_configuration(system):
    client, engine, factory, storage = system
    from sqlalchemy import text
    home = household(client)
    row = post(client, '/v1/voice-profiles', home[2], dict(family_id=home[0], owner_user_id=home[1], display_name='测试')).json()
    path = '/v1/voice-profiles/' + row['id']
    assert client.put(path + '/sample', headers=home[2], content=sample()).status_code == 200
    with engine.begin() as db:
        db.execute(text("UPDATE voice_profile SET expires_at=now()-interval '1 day'"))
    async def expire():
        from app.modules.voice.service import maintenance
        async with factory() as db:
            await maintenance(db)
            await db.commit()
        await worker.run_one(factory, storage, get_settings())
    asyncio.run(expire())
    assert not storage.objects
    assert client.get(path, headers=home[2]).json()['status'] == 'DELETED'
