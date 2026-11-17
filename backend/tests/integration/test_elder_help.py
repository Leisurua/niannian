import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.modules.signal import service as signals
from backend.tests.integration.test_notifications import drain, pref
from backend.tests.support import URL, grant, handshake, household, login, post, start, ws_frame

pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable TEST_DATABASE_URL required')
PATH = '/v1/signal-events/help-requests'


def request(client, home, key='help-1'):
    response = post(client, PATH, home[4], {'family_id': home[0]}, key=key)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def test_help_without_contacts_is_persisted_and_only_owner_can_request(system):
    client, engine, _, _ = system
    home = household(client)
    event = request(client, home)
    assert event['status'] == 'NOTIFICATION_FAILED' and event['deliveries'] == []
    assert '没有可用的已授权联系人' in event['help_message']
    assert event['recognition_mode'] == 'EXPLICIT' and not event['can_handle']
    assert event['contact_result'] == 'UNKNOWN' and 'contacts' not in event
    assert request(client, home)['id'] == event['id']
    assert post(client, PATH, home[2], {'family_id': home[0]}).status_code == 403
    _, outsider = login(client, 'demo-other')
    assert post(client, PATH, outsider, {'family_id': home[0]}).status_code == 404
    assert client.get('/v1/signal-events/' + event['id'], headers=home[2]).status_code == 404
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM signal_event')).scalar() == 1
        assert conn.execute(text('SELECT count(*) FROM notification')).scalar() == 0


def test_ble_help_replay_uses_one_request_and_current_family_authorization(system):
    client, engine, _, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home)
    body = {'family_id': home[0], 'source': 'BLE'}
    key = str(uuid4())
    first = post(client, PATH, home[4], body, key=key)
    assert first.status_code == 200 and first.json()['status'] == 'VALIDATED'
    with engine.begin() as conn:
        conn.execute(text("UPDATE signal_event SET detected_at=detected_at-interval '3 minutes'"))
    repeated = post(client, PATH, home[4], body, key=key)
    assert repeated.status_code == 200 and repeated.json()['duplicate']
    assert repeated.json()['id'] == first.json()['id']
    assert post(client, PATH, home[2], body, key=key).status_code == 403
    with engine.connect() as conn:
        assert conn.execute(text('SELECT trigger_category FROM signal_event')).scalar() == 'EXPLICIT_HELP_BLE'
        assert conn.execute(text('SELECT count(*) FROM notification')).scalar() == 1


def test_help_reuses_delivery_contacts_and_family_progress_without_claiming_connection(system):
    client, engine, factory, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home, ['IN_APP', 'PUSH'])
    event = request(client, home)
    assert len(event['deliveries']) == 2 and event['status'] == 'VALIDATED'
    drain(factory)
    path = '/v1/signal-events/' + event['id']
    detail = client.get(path, headers=home[2]).json()
    assert detail['recognition_mode'] == 'EXPLICIT' and detail['can_handle']
    assert detail['source_conversation_id'] is None
    assert detail['contact_result'] == 'UNKNOWN'
    assert any(d['simulated'] for d in detail['deliveries'])
    for action, status in [('ACKNOWLEDGE', 'NOTIFIED'), ('CONTACT', 'ACKNOWLEDGED'), ('RESOLVE', 'CONTACTED')]:
        result = post(client, path + '/actions', home[2], {'action': action, 'expected_status': status})
        assert result.status_code == 200, result.text
    progress = client.get(path, headers=home[4]).json()
    assert progress['status'] == 'RESOLVED' and progress['contact_result'] == 'UNKNOWN'
    assert [h['action'] for h in progress['history']] == ['ACKNOWLEDGE', 'CONTACT', 'RESOLVE']
    assert 'contacts' not in progress and 'source_conversation_id' not in progress
    async def maintenance():
        async with factory() as db:
            await signals.maintenance(db)
            await db.commit()
    asyncio.run(maintenance())
    assert client.get(path, headers=home[4]).status_code == 200
    with engine.connect() as conn:
        assert conn.execute(text('SELECT source_conversation_id FROM signal_event')).scalar() is None


def test_concurrent_distinct_keys_and_late_retry_do_not_resend(system):
    client, engine, _, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home)
    with ThreadPoolExecutor(max_workers=4) as pool:
        events = list(pool.map(lambda n: request(client, home, f'help-{n}'), range(4)))
    assert len({e['id'] for e in events}) == 1
    assert sum(not e['duplicate'] for e in events) == 1
    with engine.begin() as conn:
        conn.execute(text("UPDATE signal_event SET detected_at=detected_at-interval '3 minutes'"))
    assert request(client, home, 'help-0')['id'] == events[0]['id']
    new = request(client, home, 'new-request')
    assert new['id'] != events[0]['id']
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM notification')).scalar() == 2


@pytest.mark.parametrize('channels', [[], ['SMS'], ['PHONE']])
def test_disabled_or_unconfigured_channels_report_failure(system, channels):
    client, _, factory, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home, channels)
    event = request(client, home)
    drain(factory)
    progress = client.get('/v1/signal-events/' + event['id'], headers=home[4]).json()
    assert progress['status'] == 'NOTIFICATION_FAILED'
    assert '没有可用的通知渠道' in progress['help_message'] if not channels else '发送失败' in progress['help_message']
    assert progress['contact_result'] == 'UNKNOWN'


def test_revoke_before_dispatch_hides_family_event_and_cancels_send(system):
    client, engine, factory, _ = system
    home = household(client)
    consent_id = grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home)
    event = request(client, home)
    assert post(client, '/v1/consents/' + consent_id + '/revoke', home[4]).status_code == 201
    assert request(client, home)['id'] == event['id']
    drain(factory)
    assert client.get('/v1/signal-events/' + event['id'], headers=home[2]).status_code == 404
    progress = client.get('/v1/signal-events/' + event['id'], headers=home[4]).json()
    assert progress['deliveries'] == [] and '当前授权' in progress['help_message']
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM notification WHERE sent_at IS NOT NULL')).scalar() == 0


def test_explicit_voice_uses_same_request_flow_without_llm_and_dedupes_button(system, monkeypatch):
    from app.ai.conversation import MockConversationLLM
    async def fail(*args, **kwargs):
        pytest.fail('Explicit help must not call the LLM')
    monkeypatch.setattr(MockConversationLLM, 'generate', fail)
    client, engine, _, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home)
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': '我要向家人求助'}))
        event = ws.receive_json()
        assert event['type'] == 'signal.created' and event['payload']['type'] == 'EMERGENCY'
        reply = ws.receive_json()
        assert reply['type'] == 'assistant.text' and '通知等待发送' in reply['payload']['text']
        assert ws.receive_json()['payload']['state'] == 'IDLE'
    assert request(client, home)['id'] == event['payload']['signal_event_id']
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM notification')).scalar() == 1
        assert conn.execute(text('SELECT trigger_category FROM signal_event')).scalar() == 'EXPLICIT_HELP_VOICE'


def test_phone_receipt_evidence_never_advances_family_contact_state(system):
    from app.modules.notification.models import Notification
    from app.modules.notification.service import apply_receipt
    client, _, factory, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home, ['PHONE'])
    event = request(client, home)
    async def receipt(status):
        from sqlalchemy import select
        async with factory() as db:
            notice = await db.scalar(select(Notification).where(Notification.signal_event_id == UUID(event['id'])))
            # Each simulated receipt represents an independent call.
            notice.status, notice.provider_status = 'SENT', 'queued'
            apply_receipt(notice, status)
            await db.commit()
    for status in ('completed', 'no-answer', 'busy'):
        asyncio.run(receipt(status))
        progress = client.get('/v1/signal-events/' + event['id'], headers=home[4]).json()
        assert progress['deliveries'][0]['delivery_status'] == status
        assert progress['contact_result'] == 'UNKNOWN'
        assert progress['status'] not in ('CONTACTED', 'RESOLVED')


def test_help_honors_quiet_hours_and_reports_unknown_instead_of_failure(system):
    from datetime import timedelta
    from app.platform.identifiers import utcnow
    client, engine, factory, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    now = utcnow()
    pref(client, home, ['PHONE'], timezone='UTC',
        quiet_hours_start=(now - timedelta(minutes=1)).strftime('%H:%M'),
        quiet_hours_end=(now + timedelta(minutes=10)).strftime('%H:%M'))
    event = request(client, home)
    assert event['deliveries'][0]['deferred']
    drain(factory)
    with engine.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM notification_attempt')).scalar() == 0
        conn.execute(text("UPDATE notification SET status='FAILED', error_code='DELIVERY_UNKNOWN'"))
    progress = client.get('/v1/signal-events/' + event['id'], headers=home[4]).json()
    assert '结果未知' in progress['help_message'] and '发送失败' not in progress['help_message']
