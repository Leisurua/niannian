import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import text

from app.modules.conversation import proactive, summary
from app.modules.conversation.models import Conversation
from app.platform.config import get_settings
from app.platform.identifiers import utcnow
from app.worker.tasks import run_one
from backend.tests.integration.test_week3_postgres import URL, system, household, post, grant, login, ws_frame
from backend.tests.integration.test_week4_postgres import handshake, start

pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable WEEK3_TEST_DATABASE_URL required')


def self_grant(client, home):
    result = post(client, '/v1/consents', home[4], dict(family_id=home[0], subject_user_id=home[3],
        grantee_user_id=home[3], scope='CONVERSATION_SUMMARY', source='SETTINGS'))
    assert result.status_code == 201, result.text
    return result.json()['id']


def converse(client, home, utterance='你好，今天想种花', end=True):
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': utterance}))
        assert ws.receive_json()['payload']['state'] == 'THINKING'
        assert ws.receive_json()['type'] == 'assistant.text'
        assert ws.receive_json()['type'] == 'assistant.state'
        if end:
            ws.send_json(ws_frame(cid, 'session.end', 3, {'reason': 'USER'}))
            assert ws.receive_json()['type'] == 'assistant.state'
    return cid


def drain(factory):
    async def work():
        for _ in range(30):
            if not await run_one(factory):
                return
        pytest.fail('Summary tasks failed to drain')
    asyncio.run(work())


def read(client, cid, headers, reason='FAMILY_CHECK_IN'):
    return client.get('/v1/conversations/' + cid, headers={**headers, **({'X-Access-Reason': reason} if reason else {})})


def test_standing_grant_two_sessions_reason_audit_and_revoke(system):
    client, engine, factory, _ = system
    home = household(client)
    self_grant(client, home)
    sharing = grant(client, home, 'CONVERSATION_SUMMARY')
    ids = [converse(client, home), converse(client, home, '你是谁')]
    assert all(read(client, cid, home[2]).json()['summary'] is None for cid in ids)
    drain(factory)
    for cid in ids:
        assert read(client, cid, home[2], None).status_code == 422
        assert read(client, cid, home[2], 'free text').status_code == 422
        response = read(client, cid, home[2])
        assert response.status_code == 200 and response.json()['summary_status'] == 'READY'
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['summary'] in summary.TOPICS
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM consent WHERE scope='CONVERSATION_SUMMARY' AND grantee_user_id<>subject_user_id")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM consent WHERE scope='NOTIFICATION_TO_FAMILY'")).scalar() == 0
        assert set(conn.execute(text("SELECT DISTINCT kind FROM task_outbox")).scalars()) == {'CONVERSATION_SUMMARY'}
        audits = conn.execute(text("SELECT reason, metadata_redacted FROM audit_log WHERE action='CONVERSATION_READ' AND actor_user_id=:id"), {'id': home[1]}).all()
        assert len(audits) == 4 and all(row.reason == 'FAMILY_CHECK_IN' for row in audits)
        assert all(not row.metadata_redacted for row in audits)
    assert post(client, '/v1/consents/' + sharing + '/revoke', home[4]).status_code == 201
    assert all(read(client, cid, home[2]).status_code == 404 for cid in ids)
    assert all(read(client, cid, home[4], None).json()['summary'] for cid in ids)


def test_summary_denial_preserves_basic_conversation_and_never_stores_raw_text(system):
    client, engine, factory, _ = system
    home = household(client)
    grant(client, home, 'CONVERSATION_SUMMARY')
    cid = converse(client, home, 'synthetic-private-unapproved-text')
    assert post(client, '/v1/conversations/' + cid + '/summary', home[4]).status_code == 403
    with engine.connect() as conn:
        row = conn.execute(text('SELECT summary_text, provider_metadata FROM conversation')).one()
        assert row.summary_text is None and 'synthetic-private' not in str(row)
        assert conn.execute(text('SELECT count(*) FROM task_outbox')).scalar() == 0


@pytest.mark.parametrize('change', ['self_revoke', 'reader_expiry', 'owner_membership', 'reader_membership', 'deleted', 'deleted_state', 'retention', 'other_family'])
def test_summary_current_permissions_and_resource_states(system, change):
    client, engine, factory, _ = system
    home = household(client)
    own = self_grant(client, home)
    sharing = grant(client, home, 'CONVERSATION_SUMMARY')
    cid = converse(client, home)
    drain(factory)
    assert read(client, cid, home[2]).json()['summary']
    headers = home[2]
    if change == 'self_revoke':
        assert post(client, '/v1/consents/' + own + '/revoke', home[4]).status_code == 201
    elif change == 'other_family':
        _, headers = login(client, 'demo-caregiver')
    else:
        with engine.begin() as conn:
            if change == 'reader_expiry':
                conn.execute(text("UPDATE consent SET expires_at=now()-interval '1 second' WHERE id=:id"), {'id': sharing})
            elif change in ('owner_membership', 'reader_membership'):
                conn.execute(text("UPDATE family_member SET status='REVOKED' WHERE user_id=:id"), {'id': home[3] if change == 'owner_membership' else home[1]})
            elif change == 'deleted':
                conn.execute(text('UPDATE conversation SET deleted_at=now() WHERE id=:id'), {'id': cid})
            elif change == 'deleted_state':
                conn.execute(text("UPDATE conversation SET status='DELETED' WHERE id=:id"), {'id': cid})
            else:
                conn.execute(text("UPDATE conversation SET summary_retention_until=now()-interval '1 second' WHERE id=:id"), {'id': cid})
    response = read(client, cid, headers)
    if change in ('self_revoke', 'retention'):
        assert response.status_code == 200 and response.json()['summary'] is None
        drain(factory)
        with engine.connect() as conn:
            assert conn.execute(text('SELECT summary_text FROM conversation WHERE id=:id'), {'id': cid}).scalar() is None
    else:
        assert response.status_code == 404


def test_empty_failure_no_raw_fallback_dead_task_and_old_version_fence(system):
    client, engine, factory, _ = system
    home = household(client); own = self_grant(client, home)
    empty = start(client, home)
    assert post(client, '/v1/conversations/' + empty + '/summary', home[4]).json()['status'] == 'FAILED'
    cid = converse(client, home)
    async def prepare():
        async with factory() as db:
            row = await db.get(Conversation, UUID(cid))
            result = row.summary_version, await summary.prepare(db, row.id, row.summary_version)
            await db.commit()
            return result
    version, prepared = asyncio.run(prepare())
    assert post(client, '/v1/consents/' + own + '/revoke', home[4]).status_code == 201
    async def stale():
        async with factory() as db:
            await summary.complete(db, UUID(cid), version, prepared)
            await db.commit()
    asyncio.run(stale()); drain(factory)
    assert read(client, cid, home[4], None).json()['summary'] is None
    self_grant(client, home)
    cid2 = converse(client, home)
    with engine.begin() as conn:
        conn.execute(text("UPDATE task_outbox SET status='DEAD' WHERE resource_id=:id AND kind='CONVERSATION_SUMMARY'"), {'id': cid2})
    async def maintenance():
        async with factory() as db:
            await summary.maintenance(db); await db.commit()
    asyncio.run(maintenance())
    result = read(client, cid2, home[4], None).json()
    assert result['summary_status'] == 'FAILED' and result['summary'] is None


def preferences(client, home):
    path = f'/v1/families/{home[0]}/proactive-preferences/{home[3]}'
    body = dict(timezone='UTC', window_start='00:00', window_end='23:59', daily_cap=3)
    assert client.get(path, headers=home[4]).json()['daily_cap'] == 0
    result = client.put(path, headers={**home[2], 'If-Match': '1'}, json=body)
    assert result.status_code == 200, result.text
    return path, body, result.json()['version']


def test_proactive_joint_confirmation_version_idempotency_and_owner_only_pause(system):
    client, engine, factory, _ = system
    home = household(client); path, body, version = preferences(client, home)
    assert post(client, path + '/confirm', home[2], {'version': version}).status_code == 403
    assert post(client, path + '/confirm', home[4], {'version': version - 1}).status_code == 409
    assert post(client, path + '/confirm', home[4], {'version': version}, key='confirm').json()['confirmed']
    assert post(client, path + '/confirm', home[4], {'version': version}, key='confirm').json()['confirmed']
    assert post(client, path + '/confirm', home[4], {'version': version + 1}, key='confirm').status_code == 409
    assert post(client, path + '/pause-today', home[2]).status_code == 403
    assert post(client, path + '/pause-today', home[4], key='pause').json()['paused_on']
    assert post(client, path + '/pause-today', home[4], key='pause').status_code == 200
    assert client.put(path, headers={**home[2], 'If-Match': str(version)}, json=body | {'daily_cap': 2}).json()['confirmed'] is False
    assert client.put(path, headers={**home[2], 'If-Match': str(version)}, json=body).status_code == 409
    assert client.put(path, headers={**home[2], 'If-Match': str(version + 1)}, json=body | {'daily_cap': 4}).status_code == 422


def test_proactive_no_socket_no_quota_concurrent_claim_pause_and_timezone_carry(system):
    client, engine, factory, _ = system
    home = household(client); path, body, version = preferences(client, home)
    post(client, path + '/confirm', home[4], {'version': version})
    cid = converse(client, home, end=False)
    now = utcnow()
    with engine.begin() as conn:
        conn.execute(text("UPDATE conversation SET started_at=now()-interval '1 hour' WHERE id=:id"), {'id': cid})
    async def tick(now=now):
        async with factory() as db:
            await proactive.tick(db, get_settings(), now); await db.commit()
    asyncio.run(tick())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM proactive_daily_counter')).scalar() == 0
    with engine.connect() as lease:
        lease.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': proactive.lock_id(UUID(cid))})
        async def race():
            await asyncio.gather(tick(), tick())
        asyncio.run(race())
        with engine.connect() as conn:
            assert conn.execute(text('SELECT sum(used_count) FROM proactive_daily_counter')).scalar() == 1
        post(client, path + '/pause-today', home[4])
        asyncio.run(tick(now + timedelta(minutes=31)))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT sum(used_count) FROM proactive_daily_counter')).scalar() == 1
    updated = client.put(path, headers={**home[2], 'If-Match': str(version)}, json=body | {'timezone': 'Asia/Shanghai'})
    assert updated.status_code == 200 and updated.json()['paused_on']
    with engine.connect() as conn:
        assert conn.execute(text('SELECT max(used_count) FROM proactive_daily_counter')).scalar() >= 1


def test_worker_notification_rechecked_by_live_socket_and_pause_text(system, monkeypatch):
    from app.modules.conversation import api
    client, engine, factory, _ = system
    home = household(client); path, _, version = preferences(client, home)
    post(client, path + '/confirm', home[4], {'version': version})
    cid = start(client, home)
    old = utcnow() - timedelta(hours=1)
    monkeypatch.setattr(api, 'utcnow', lambda: old)
    with engine.begin() as conn:
        conn.execute(text('UPDATE conversation SET started_at=:old WHERE id=:id'), {'old': old, 'id': cid})
    async def tick():
        async with factory() as db:
            await proactive.tick(db, get_settings()); await db.commit()
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        asyncio.run(tick())
        event = ws.receive_json()
        assert event['type'] == 'assistant.text' and event['payload']['text'] == proactive.INVITATION
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': '今天少打扰我'}))
        assert '今天已减少' in ws.receive_json()['payload']['text']
        assert ws.receive_json()['type'] == 'assistant.state'
    assert client.get(path, headers=home[4]).json()['paused_on']


def test_named_reader_needs_summary_permission_and_live_processing_grant(system):
    client, engine, factory, _ = system
    home = household(client); self_grant(client, home)
    reader, headers = login(client, 'demo-caregiver')
    invitation = post(client, f'/v1/families/{home[0]}/invitations', home[2], dict(target_role='CAREGIVER',
        expires_at=(utcnow() + timedelta(hours=1)).isoformat())).json()['token']
    assert post(client, f'/v1/family-invitations/{invitation}/accept', headers, {'confirm_identity': True}).status_code == 200
    cid = converse(client, home); drain(factory)
    grant_body = dict(family_id=home[0], subject_user_id=home[3], grantee_user_id=reader, scope='CONVERSATION_SUMMARY', source='SETTINGS')
    assert post(client, '/v1/consents', home[4], grant_body).status_code == 201
    assert read(client, cid, headers).status_code == 404
    with engine.begin() as conn:
        conn.execute(text('UPDATE family_member SET permission_codes=CAST(:codes AS jsonb) WHERE user_id=:id'),
            {'codes': '{"SUMMARY_READ":true}', 'id': reader})
    assert read(client, cid, headers).json()['summary']
    assert read(client, cid, home[2]).status_code == 404
    with engine.begin() as conn:
        conn.execute(text("UPDATE consent SET expires_at=now()-interval '1 second' WHERE subject_user_id=grantee_user_id AND scope='CONVERSATION_SUMMARY'"))
    assert read(client, cid, headers).json()['summary'] is None


def test_retention_does_not_extend_and_missing_deadline_is_hidden(system):
    client, engine, factory, _ = system
    home = household(client); self_grant(client, home)
    cid = converse(client, home)
    with engine.connect() as conn:
        initial = conn.execute(text('SELECT summary_retention_until FROM conversation WHERE id=:id'), {'id': cid}).scalar()
        assert utcnow() < initial <= utcnow() + timedelta(hours=24)
    for _ in range(2):
        assert post(client, f'/v1/conversations/{cid}/summary', home[4]).status_code == 202
    drain(factory)
    with engine.begin() as conn:
        assert conn.execute(text('SELECT summary_retention_until FROM conversation WHERE id=:id'), {'id': cid}).scalar() == initial
        conn.execute(text('UPDATE conversation SET summary_retention_until=NULL WHERE id=:id'), {'id': cid})
    assert read(client, cid, home[4], None).json()['summary'] is None


def test_reserved_invitation_rechecks_pause_version_and_timestamp(system):
    client, engine, factory, _ = system
    home = household(client); path, body, version = preferences(client, home)
    post(client, path + '/confirm', home[4], {'version': version})
    cid = converse(client, home, end=False)
    now = utcnow(); old = now - timedelta(hours=1)
    with engine.begin() as conn:
        conn.execute(text('UPDATE conversation SET started_at=:old WHERE id=:id'), {'old': old, 'id': cid})
    async def reserve():
        async with factory() as db:
            await proactive.tick(db, get_settings(), now); await db.commit()
    with engine.connect() as lease:
        lease.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': proactive.lock_id(UUID(cid))})
        asyncio.run(reserve())
    import json
    payload = json.dumps(dict(version=version, stamp=now.isoformat()))
    async def check(payload=payload):
        async with factory() as db:
            row = await db.get(Conversation, UUID(cid))
            value = await proactive.accept(db, row, payload, old)
            await db.commit()
            return value
    assert asyncio.run(check())
    assert not asyncio.run(check(json.dumps(dict(version=version, stamp=old.isoformat()))))
    post(client, path + '/pause-today', home[4])
    assert not asyncio.run(check())
    updated = client.put(path, headers={**home[2], 'If-Match': str(version)}, json=body).json()
    post(client, path + '/confirm', home[4], {'version': updated['version']})
    assert not asyncio.run(check())


def test_listener_failure_closes_and_releases_socket_lease(system, monkeypatch):
    from app.modules.conversation import api
    from starlette.websockets import WebSocketDisconnect
    client, _, _, _ = system
    home = household(client); cid = start(client, home)
    async def failed_listener(connection, queue):
        raise RuntimeError('fictional listener failure')
    with monkeypatch.context() as patch:
        patch.setattr(api, 'listen_proactive', failed_listener)
        with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
            assert ws.receive_json()['type'] == 'session.ready'
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
    assert not api._connections
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
