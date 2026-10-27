import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

import pytest
from app.ai.signal_candidates import extract_mock
from app.integrations.mock import MockPush
from app.modules.notification import service as notifications
from app.modules.signal import service as signals
from app.platform import tasks
from app.platform.identifiers import utcnow
from app.worker.tasks import run_one
from sqlalchemy import select, text

from backend.tests.support import (
    URL,
    grant,
    handshake,
    household,
    login,
    post,
    start,
    ws_frame,
)

pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable TEST_DATABASE_URL required')
UTTERANCE = '有人让我把验证码告诉他，还说别告诉孩子。'


def pref(client, home, channels=None, **changes):
    path = f'/v1/families/{home[0]}/notification-preferences/{home[3]}'
    old = client.get(path, headers=home[2])
    assert old.status_code == 200
    result = client.put(path, headers={**home[2], 'If-Match': str(old.json()['version'])}, json=dict(
        channels=['IN_APP'] if channels is None else channels, timezone='Asia/Shanghai',
        quiet_hours_start=None, quiet_hours_end=None) | changes)
    assert result.status_code == 200, result.text
    return result


def emit(factory, home, cid, utterance=UTTERANCE, request_id='turn-2', mutate=None):
    async def command():
        candidates = extract_mock(utterance, conversation_id=UUID(cid), message_id=uuid5(UUID(cid), request_id))
        if mutate:
            candidates = mutate(candidates)
        async with factory() as db:
            result = await signals.record_turn(db, SimpleNamespace(user_id=UUID(home[3])), UUID(cid),
                request_id, utterance, candidates)
            await db.commit()
            return result
    return asyncio.run(command())


def drain(factory, push=None):
    async def work():
        for _ in range(30):
            if not await run_one(factory, push=push):
                return
        pytest.fail('Worker did not drain')
    asyncio.run(work())


def setup_event(system, channels=None, utterance=UTTERANCE):
    client, engine, factory, _ = system
    home = household(client)
    consent_id = grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home, channels)
    cid = start(client, home)
    result = emit(factory, home, cid, utterance)
    return home, cid, consent_id, result


def test_mobile_inbox_contains_only_unread_authorized_routes(system):
    client, engine, factory, _ = system
    home, _, _, events = setup_event(system, channels=['IN_APP', 'PUSH'])
    path = '/v1/notifications/mobile-inbox'
    assert client.get(path, headers=home[2]).json()['items'] == []
    drain(factory)
    response = client.get(path, headers=home[2])
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    route, = response.json()['items']
    assert route == dict(id=route['id'], signal_event_id=events[0]['signal_event_id'],
        family_id=home[0], owner_user_id=home[3])
    assert client.get(path, headers=home[4]).json()['items'] == []
    _, outsider = login(client, 'demo-other')
    assert client.get(path, headers=outsider).json()['items'] == []
    assert client.get('/v1/notifications/' + route['id'], headers=outsider).status_code == 404
    detail = client.get('/v1/notifications/' + route['id'], headers=home[2]).json()
    assert detail['family_id'] == home[0] and detail['owner_user_id'] == home[3]
    assert detail['status'] == 'SENT'
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM notification WHERE read_at IS NOT NULL OR delivered_at IS NOT NULL")).scalar() == 0
    assert post(client, '/v1/notifications/' + route['id'] + '/read', home[2]).status_code == 200
    assert client.get(path, headers=home[2]).json()['items'] == []
    assert client.get('/v1/signal-events/' + route['signal_event_id'], headers=home[2]).json()['status'] == 'NOTIFIED'


@pytest.mark.parametrize('change', ['revoke', 'channel', 'quiet', 'handled', 'source', 'member', 'expired'])
def test_mobile_inbox_rechecks_published_notifications(system, change):
    client, engine, factory, _ = system
    home, _, consent_id, events = setup_event(system)
    drain(factory)
    path = '/v1/notifications/mobile-inbox'
    route, = client.get(path, headers=home[2]).json()['items']
    if change == 'revoke':
        assert post(client, '/v1/consents/' + consent_id + '/revoke', home[4]).status_code == 201
    elif change == 'channel':
        pref(client, home, channels=[])
    elif change == 'quiet':
        now = utcnow()
        pref(client, home, timezone='UTC', quiet_hours_start=(now - timedelta(minutes=1)).strftime('%H:%M'),
            quiet_hours_end=(now + timedelta(minutes=10)).strftime('%H:%M'))
    elif change == 'handled':
        assert post(client, '/v1/signal-events/' + events[0]['signal_event_id'] + '/actions', home[2],
            {'action': 'ACKNOWLEDGE', 'expected_status': 'NOTIFIED'}).status_code == 200
    else:
        with engine.begin() as conn:
            if change == 'source':
                conn.execute(text('UPDATE conversation SET deleted_at=now()'))
            elif change == 'expired':
                conn.execute(text("UPDATE notification SET retention_until=now()-interval '1 second', created_at=now()-interval '2 seconds'"))
            else:
                conn.execute(text("UPDATE family_member SET status='REVOKED' WHERE user_id=:id"), {'id': home[1]})
    assert client.get(path, headers=home[2]).json()['items'] == []
    if change in ('revoke', 'source', 'member', 'expired'):
        assert client.get('/v1/notifications/' + route['id'], headers=home[2]).status_code == 404


@pytest.mark.parametrize('utterance', [UTTERANCE, '我胸口有点不舒服。'])
def test_elder_sees_actual_family_progress_without_family_only_details(system, utterance):
    client, engine, factory, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    grant(client, home, 'HEALTH_MEDICATION')
    pref(client, home)
    event, = emit(factory, home, start(client, home), utterance)
    drain(factory)
    path = '/v1/signal-events/' + event['signal_event_id']
    for action, before, after in [('ACKNOWLEDGE', 'NOTIFIED', 'ACKNOWLEDGED'),
        ('CONTACT', 'ACKNOWLEDGED', 'CONTACTED'), ('RESOLVE', 'CONTACTED', 'RESOLVED')]:
        handled = post(client, path + '/actions', home[2], {'action': action, 'expected_status': before})
        assert handled.status_code == 200
        progress = client.get(path, headers=home[4]).json()
        assert progress['status'] == after and progress['can_handle'] is False
        assert progress['actioned_at'] == handled.json()['actioned_at']
        assert progress['history'][-1]['action'] == action
        assert not {'reason', 'source_conversation_id', 'contacts', 'last_action_by'} & progress.keys()
        listing = client.get('/v1/signal-events', params={'family_id': home[0]}, headers=home[4]).json()['items']
        assert listing[0]['status'] == after
    assert progress['resolved_at'] == handled.json()['resolved_at']
    assert post(client, path + '/actions', home[4], {'action': 'RESOLVE', 'expected_status': 'RESOLVED'}).status_code == 404
    with engine.begin() as conn:
        conn.execute(text('UPDATE conversation SET deleted_at=now()'))
    assert client.get(path, headers=home[4]).status_code == 404


@pytest.mark.parametrize('scope', ['CONVERSATION_SUMMARY','NOTIFICATION_TO_FAMILY'])
def test_summary_and_notification_grants_are_independent(system, scope):
    client, engine, factory, _ = system
    home = household(client)
    grant(client, home, scope)
    pref(client, home)
    cid = start(client, home)
    events = emit(factory, home, cid)
    drain(factory)
    expected = int(scope == 'NOTIFICATION_TO_FAMILY')
    assert len(events) == expected
    assert len(client.get('/v1/notifications', headers=home[2]).json()['items']) == expected
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM signal_event')).scalar() == expected
        assert conn.execute(text('SELECT count(*) FROM notification')).scalar() == expected
    if expected:
        assert client.get('/v1/conversations/' + cid, headers={**home[2],'X-Access-Reason':'FAMILY_CHECK_IN'}).status_code == 404


def test_wss_to_inapp_minimal_event_and_idempotent_read(system):
    client, engine, factory, _ = system
    home = household(client)
    grant(client, home, 'NOTIFICATION_TO_FAMILY')
    pref(client, home)
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': UTTERANCE}))
        frames = [ws.receive_json() for _ in range(5)]
        assert [f['type'] for f in frames] == ['assistant.state','warning','signal.created','assistant.text','assistant.state']
        event_id = frames[2]['payload']['signal_event_id']
        assert '已通知' not in str(frames)
    drain(factory)
    inbox = client.get('/v1/notifications', headers=home[2])
    assert inbox.headers['cache-control'] == 'no-store'
    item, = inbox.json()['items']
    assert item['status'] == 'SENT' and item['signal_event_id'] == event_id
    assert 'Mock' in item['summary'] and UTTERANCE not in str(item)
    detail = client.get('/v1/signal-events/' + event_id, headers=home[2])
    assert detail.json()['reason']['category'] == 'VERIFICATION_CODE_AND_SECRECY'
    assert detail.json()['status'] == 'NOTIFIED'
    assert 'confidence' not in detail.json() and 'source_message_id' not in detail.json()
    before = client.get('/v1/notifications/' + item['id'], headers=home[2]).json()
    assert before['status'] == 'SENT'
    a = post(client, '/v1/notifications/' + item['id'] + '/read', home[2], key='read-once')
    b = post(client, '/v1/notifications/' + item['id'] + '/read', home[2], key='read-once')
    assert a.status_code == b.status_code == 200 and a.json()['read_at'] == b.json()['read_at']
    assert a.json()['status'] == 'READ'
    own = client.get('/v1/signal-events/' + event_id, headers=home[4]).json()
    assert 'reason' not in own and 'source_conversation_id' not in own
    assert client.get('/v1/notifications/' + item['id'], headers=home[4]).status_code == 404
    with engine.connect() as conn:
        row = conn.execute(text('SELECT delivered_at,provider FROM notification')).one()
        assert row == (None, 'mock')
        assert conn.execute(text('SELECT source_message_id FROM signal_event')).scalar() is None


def test_health_requires_its_own_scope_and_never_diagnoses(system):
    client, engine, factory, _ = system
    home, cid, _, events = setup_event(system, utterance='我胸口有点不舒服。')
    assert events == []
    grant(client, home, 'HEALTH_MEDICATION')
    events = emit(factory, home, cid, '我胸口有点不舒服。')
    assert len(events) == 1
    drain(factory)
    value = client.get('/v1/signal-events/' + events[0]['signal_event_id'], headers=home[2]).json()
    assert '身体不舒服' in value['summary'] and '诊断' not in value['summary']
    with engine.connect() as conn:
        assert conn.execute(text('SELECT confidence FROM signal_event')).scalar() is None


@pytest.mark.parametrize('reason', ['revoke','expire','member','source','subject','family','recipient'])
def test_queued_delivery_rechecks_authorization_and_source(system, reason):
    client, engine, factory, _ = system
    home, cid, consent_id, events = setup_event(system)
    with engine.connect() as conn:
        nid = str(conn.execute(text('SELECT id FROM notification')).scalar())
    if reason == 'revoke':
        assert post(client, '/v1/consents/' + consent_id + '/revoke', home[4], {'reason':'测试撤回'}).status_code == 201
    else:
        with engine.begin() as conn:
            if reason == 'expire':
                conn.execute(text("UPDATE consent SET expires_at=now()-interval '1 second'"))
            elif reason == 'member':
                conn.execute(text("UPDATE family_member SET status='REVOKED' WHERE user_id=:id"), {'id':home[1]})
            elif reason == 'source':
                conn.execute(text("UPDATE conversation SET status='DELETED',deleted_at=now()"))
            elif reason in ('subject','recipient'):
                conn.execute(text("UPDATE \"user\" SET global_status='SUSPENDED' WHERE id=:id"), {'id':home[3] if reason=='subject' else home[1]})
            else:
                conn.execute(text("UPDATE family SET status='DELETED',deleted_at=now()"))
    drain(factory)
    assert client.get('/v1/notifications/' + nid, headers=home[2]).status_code in (401,404)
    assert client.get('/v1/signal-events/' + events[0]['signal_event_id'], headers=home[2]).status_code in (401,404)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM notification WHERE status IN ('SENT','DELIVERED','READ')")).scalar() == 0
        assert conn.execute(text('SELECT count(*) FROM notification_attempt')).scalar() == 0


def test_cross_family_recipient_and_ungranted_member_hidden(system):
    client, _, factory, _ = system
    home, _, _, events = setup_event(system)
    other, oh = login(client, 'demo-caregiver')
    invite = post(client, f'/v1/families/{home[0]}/invitations', home[2],
        {'target_role':'CAREGIVER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()['token']
    assert post(client, '/v1/family-invitations/' + invite + '/accept', oh, {'confirm_identity':True}).status_code == 200
    outsider, outside_headers = login(client, 'demo-other')
    drain(factory)
    nid = client.get('/v1/notifications', headers=home[2]).json()['items'][0]['id']
    for headers in (oh, outside_headers):
        assert client.get('/v1/signal-events', headers=headers).json()['items'] == []
        assert client.get('/v1/signal-events/' + events[0]['signal_event_id'], headers=headers).status_code == 404
        assert client.get('/v1/notifications/' + nid, headers=headers).status_code == 404


def test_concurrent_dedup_and_changed_category_severity(system):
    client, engine, factory, _ = system
    home, cid, _, _ = setup_event(system)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda n: emit(factory, home, cid, request_id='turn-'+str(n+3)), range(8)))
    assert results == [[]]*8
    assert len(emit(factory, home, cid, '马上转账到这个账户', request_id='turn-11')) == 1
    assert len(emit(factory, home, cid, '转账保密', request_id='turn-12')) == 1
    drain(factory)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM signal_event')).scalar() == 3
        assert conn.execute(text('SELECT count(*) FROM notification')).scalar() == 3


def test_forged_candidates_and_emergency_never_create_events(system):
    client, engine, factory, _ = system
    home = household(client); grant(client, home, 'NOTIFICATION_TO_FAMILY')
    cid = start(client, home)
    assert emit(factory, home, cid, mutate=lambda cs: (cs[0].model_copy(update={'source_message_id':uuid4()}),)) == []
    assert emit(factory, home, cid, '验证码是什么东西？') == []
    assert emit(factory, home, cid, '救命，帮我叫人。') == []
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM signal_event')).scalar() == 0


class FailedPush(MockPush):
    async def send(self, request):
        raise RuntimeError('synthetic-private-provider-body')


def test_mock_push_retry_exhaustion_and_independent_inapp_success(system):
    client, engine, factory, _ = system
    home, _, _, events = setup_event(system, channels=['IN_APP','PUSH'])
    for _ in range(5):
        drain(factory, FailedPush())
        with engine.begin() as conn:
            conn.execute(text("UPDATE task_outbox SET available_at=now()-interval '1 second' WHERE status='RETRY'"))
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT channel,status,delivered_at FROM notification ORDER BY channel')).all()
        assert rows == [('IN_APP','SENT',None),('PUSH','FAILED',None)]
        assert conn.execute(text("SELECT count(*) FROM notification_attempt WHERE provider='mock'")).scalar() == 6
        assert conn.execute(text("SELECT count(*) FROM task_outbox WHERE status='DEAD'")).scalar() == 1
        assert 'synthetic-private-provider-body' not in str(conn.execute(text('SELECT error_detail_redacted FROM notification_attempt')).all())
    assert client.get('/v1/signal-events/'+events[0]['signal_event_id'],headers=home[2]).json()['status']=='NOTIFIED'


def test_mock_push_success_is_sent_not_delivered(system):
    client, engine, factory, _ = system
    setup_event(system, channels=['PUSH'])
    drain(factory)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status,provider,delivered_at FROM notification')).one() == ('SENT','mock',None)


def test_revoke_during_provider_io_prevents_completion_and_regrant_resurrection(system):
    client, engine, factory, _ = system
    home, _, consent_id, _ = setup_event(system, channels=['PUSH'])
    completed = []
    class RevokePush(MockPush):
        async def send(self, request):
            result = await asyncio.to_thread(post, client, '/v1/consents/'+consent_id+'/revoke', home[4], {'reason':'撤回'})
            assert result.status_code == 201
            await asyncio.to_thread(grant, client, home, 'NOTIFICATION_TO_FAMILY')
            completed.append(True)
            return await super().send(request)
    drain(factory, RevokePush())
    assert completed == [True]
    assert client.get('/v1/notifications', headers=home[2]).json()['items']==[]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM notification WHERE status='SENT'")).scalar()==0


def test_quiet_hours_postpone_without_using_attempt_and_expired_queue_cancels(system):
    client, engine, factory, _ = system
    home, _, _, _ = setup_event(system)
    from zoneinfo import ZoneInfo
    now = utcnow().astimezone(ZoneInfo('Asia/Shanghai'))
    pref(client, home, quiet_hours_start=(now-timedelta(hours=1)).strftime('%H:%M'),
        quiet_hours_end=(now+timedelta(hours=1)).strftime('%H:%M'))
    drain(factory)
    with engine.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM notification_attempt')).scalar()==0
        assert conn.execute(text('SELECT attempts FROM task_outbox')).scalar()==0
        conn.execute(text("UPDATE notification SET created_at=now()-interval '2 days', dispatch_deadline=now()-interval '1 second'"))
        conn.execute(text("UPDATE task_outbox SET available_at=now()-interval '1 second'"))
    drain(factory)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM notification')).scalar()=='CANCELLED'


def test_expiry_invisible_then_worker_cleans_attempt_notification_event(system):
    client, engine, factory, _ = system
    home, _, _, events = setup_event(system)
    drain(factory)
    with engine.begin() as conn:
        conn.execute(text("UPDATE signal_event SET detected_at=now()-interval '8 days',retention_until=now()-interval '1 second'"))
    assert client.get('/v1/notifications',headers=home[2]).json()['items']==[]
    async def maintain():
        async with factory() as db:
            await signals.maintenance(db)
            await notifications.maintenance(db)
            await db.commit()
    asyncio.run(maintain()); drain(factory)
    with engine.connect() as conn:
        for table in ('notification_attempt','notification','signal_event'):
            assert conn.execute(text('SELECT count(*) FROM '+table)).scalar()==0


def test_stale_lease_cannot_complete_notification(system):
    client, engine, factory, _ = system
    setup_event(system, channels=['PUSH'])
    class ExpireLease(MockPush):
        async def send(self, request):
            with engine.begin() as conn:
                conn.execute(text("UPDATE task_outbox SET lease_until=now()-interval '1 second' WHERE status='RUNNING'"))
            return await super().send(request)
    asyncio.run(run_one(factory,push=ExpireLease()))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM notification')).scalar()=='QUEUED'
    drain(factory)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM notification')).scalar()=='SENT'
        assert conn.execute(text('SELECT status FROM notification_attempt ORDER BY attempt_no')).scalars().all()==['FAILED','SUCCEEDED']


def test_preferences_version_validation_and_no_delegated_recipient(system):
    client, engine, _, _ = system
    home=household(client)
    path=f'/v1/families/{home[0]}/notification-preferences/{home[3]}'
    initial=client.get(path,headers=home[2]).json()
    assert initial['version']==0 and initial['channels']==['IN_APP']
    pref(client,home)
    body=dict(channels=['PUSH'],timezone='Asia/Shanghai')
    assert client.put(path,headers={**home[2],'If-Match':'0'},json=body).status_code==409
    for change in ({'channels':['EMAIL']},{'channels':['PUSH','PUSH']},{'timezone':'invalid'},
                   {'recipient_user_id':home[3]},{'quiet_hours_start':'22:00'}):
        assert client.put(path,headers={**home[2],'If-Match':'1'},json=body|change).status_code==422
    assert client.get(path,headers=home[4]).status_code==403
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM consent')).scalar()==0


def test_replayed_source_turn_stays_deduplicated_across_new_time_bucket(system, monkeypatch):
    client, engine, factory, _ = system
    home, cid, _, _ = setup_event(system)
    assert emit(factory, home, cid, request_id='turn-3')==[]
    later=utcnow()+timedelta(minutes=31)
    monkeypatch.setattr(signals,'utcnow',lambda:later)
    assert emit(factory, home, cid, request_id='turn-2')==[]
    assert emit(factory, home, cid, request_id='turn-3')==[]
    assert len(emit(factory,home,cid,request_id='turn-4'))==1
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM signal_event')).scalar()==2


def test_only_failed_push_sets_event_failure_and_pagination_remains_authorized(system):
    client, engine, factory, _ = system
    home, cid, _, events=setup_event(system,channels=['PUSH'])
    for _ in range(5):
        drain(factory, FailedPush())
        with engine.begin() as conn:
            conn.execute(text("UPDATE task_outbox SET available_at=now()-interval '1 second' WHERE status='RETRY'"))
    assert client.get('/v1/signal-events/'+events[0]['signal_event_id'],headers=home[2]).json()['status']=='NOTIFICATION_FAILED'
    emit(factory,home,cid,'转账保密',request_id='turn-3'); drain(factory)
    page=client.get('/v1/notifications?limit=1',headers=home[2]).json()
    assert page['page']['has_more']
    next_page=client.get('/v1/notifications',params={'limit':1,'cursor':page['page']['next_cursor']},headers=home[2]).json()
    assert len(next_page['items'])==1 and next_page['items'][0]['id']!=page['items'][0]['id']
    assert client.get('/v1/notifications',params={'limit':1,'channel':'IN_APP','cursor':page['page']['next_cursor']},headers=home[2]).status_code==400


def test_named_recipient_revoke_does_not_cancel_other_grantee(system):
    client, engine, factory, _ = system
    home=household(client)
    first_grant=grant(client,home,'NOTIFICATION_TO_FAMILY')
    other,headers=login(client,'demo-caregiver')
    invite=post(client,f'/v1/families/{home[0]}/invitations',home[2],{'target_role':'CAREGIVER',
        'expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()['token']
    assert post(client,'/v1/family-invitations/'+invite+'/accept',headers,{'confirm_identity':True}).status_code==200
    second=(home[0],other,headers,home[3],home[4])
    grant(client,second,'NOTIFICATION_TO_FAMILY')
    cid=start(client,home)
    event=emit(factory,home,cid)[0]['signal_event_id']
    assert client.get('/v1/signal-events/'+event,headers=headers).status_code==404
    with engine.begin() as conn:
        conn.execute(text('UPDATE family_member SET permission_codes=CAST(:codes AS jsonb) WHERE user_id=:id'),
            {'id':other,'codes':'{"SIGNAL_READ":true}'})
    pref(client,home); pref(client,second)
    emit(factory,home,cid,'转账保密',request_id='turn-3')
    assert post(client,'/v1/consents/'+first_grant+'/revoke',home[4]).status_code==201
    drain(factory)
    assert client.get('/v1/notifications',headers=home[2]).json()['items']==[]
    items=client.get('/v1/notifications',headers=headers).json()['items']
    assert len(items)==1 and items[0]['status']=='SENT'


def test_summary_revoke_does_not_cancel_independent_notification(system):
    client, engine, factory, _ = system
    home,cid,_,events=setup_event(system)
    summary_grant=grant(client,home,'CONVERSATION_SUMMARY')
    assert post(client,'/v1/consents/'+summary_grant+'/revoke',home[4]).status_code==201
    drain(factory)
    assert len(client.get('/v1/notifications',headers=home[2]).json()['items'])==1
    assert client.get('/v1/conversations/'+cid,headers={**home[2],'X-Access-Reason':'FOLLOW_UP'}).status_code==404


@pytest.mark.parametrize('failure',['timeout','fake_delivery'])
def test_provider_timeout_or_delivery_claim_fails_closed(system,failure):
    client,engine,factory,_=system
    setup_event(system,channels=['PUSH'])
    class InvalidPush(MockPush):
        async def send(self,request):
            if failure=='timeout':
                raise TimeoutError('synthetic provider timeout')
            return (await super().send(request)).model_copy(update={'delivery_observed':True})
    drain(factory,InvalidPush())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status,delivered_at FROM notification')).one()==('QUEUED',None)
        assert conn.execute(text('SELECT status FROM notification_attempt')).scalar()=='RETRY_SCHEDULED'


def test_exhausted_abandoned_lease_becomes_observable_failure(system):
    client,engine,factory,_=system
    home,_,_,events=setup_event(system,channels=['PUSH'])
    async def abandon():
        async with factory() as db:
            task=await tasks.claim(db)
            await notifications.prepare(db,task.id,task.lease_token,task.resource_id)
            task.attempts=task.max_attempts
            task.lease_until=utcnow()-timedelta(seconds=1)
            await db.commit()
        await run_one(factory)
        async with factory() as db:
            await notifications.maintenance(db)
            await db.commit()
    asyncio.run(abandon())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status,error_code FROM notification')).one()==('FAILED','LEASE_EXHAUSTED')
        assert conn.execute(text('SELECT status FROM notification_attempt')).scalar()=='FAILED'
    assert client.get('/v1/signal-events/'+events[0]['signal_event_id'],headers=home[2]).json()['status']=='NOTIFICATION_FAILED'


@pytest.mark.parametrize('change',['unvalidated','owner_role'])
def test_unvalidated_event_or_changed_owner_role_stays_invisible(system,change):
    client,engine,factory,_=system
    home,_,_,events=setup_event(system)
    with engine.begin() as conn:
        if change=='unvalidated':
            conn.execute(text("UPDATE signal_event SET status='DETECTED'"))
        else:
            conn.execute(text("UPDATE family_member SET role='CHILD' WHERE user_id=:id"),{'id':home[3]})
    drain(factory)
    assert client.get('/v1/signal-events/'+events[0]['signal_event_id'],headers=home[2]).status_code==404
    assert client.get('/v1/notifications',headers=home[2]).json()['items']==[]


def test_standalone_worker_process_publishes_inapp_notification(system):
    import os
    import subprocess
    import sys
    client,engine,_,_=system
    home,_,_,_=setup_event(system)
    completed=subprocess.run([sys.executable,'-m','app.worker.main','--once'],
        env={**os.environ,'APP_ENV':'test','PROVIDER_MODE':'mock','DATABASE_URL':URL},
        capture_output=True,timeout=40)
    assert completed.returncode==0
    assert client.get('/v1/notifications',headers=home[2]).json()['items'][0]['status']=='SENT'


def test_signal_confirmation_contact_resolution_and_replay(system):
    client, engine, factory, _ = system
    home, _, _, events = setup_event(system)
    drain(factory)
    path = '/v1/signal-events/' + events[0]['signal_event_id']
    detail = client.get(path, headers=home[2]).json()
    assert detail['can_handle'] and detail['status'] == 'NOTIFIED'
    body = {'action': 'ACKNOWLEDGE', 'expected_status': 'NOTIFIED'}
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: post(client, path + '/actions', home[2], body, key='ack-once'), range(3)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()['actioned_at'] for r in responses}) == 1
    first_time = responses[0].json()['actioned_at']
    assert post(client, path + '/actions', home[2], body).json()['actioned_at'] == first_time
    conflict = post(client, path + '/actions', home[2], {'action': 'CONTACT', 'expected_status': 'NOTIFIED'})
    assert conflict.status_code == 409
    contact = post(client, path + '/actions', home[2], {'action': 'CONTACT', 'expected_status': 'ACKNOWLEDGED'}, key='contact-once')
    assert contact.status_code == 200 and contact.json()['status'] == 'CONTACTED'
    resolved = post(client, path + '/actions', home[2], {'action': 'RESOLVE', 'expected_status': 'CONTACTED'}, key='resolve-once')
    assert resolved.status_code == 200
    assert resolved.json()['resolved_at'] == resolved.json()['actioned_at']
    assert resolved.json()['resolution_code'] == 'FAMILY_CONFIRMED'
    assert client.get(path, headers=home[2]).json()['status'] == 'RESOLVED'
    assert post(client, path + '/actions', home[2], body, key='ack-once').json()['status'] == 'RESOLVED'
    assert post(client, path + '/actions', home[2], body).status_code == 409
    assert post(client, path + '/actions', home[2], {'action': 'CONTACT', 'expected_status': 'RESOLVED'}, key='ack-once').status_code == 409
    # Resolved events and published notifications remain readable within their original retention.
    item = client.get('/v1/notifications', headers=home[2]).json()['items'][0]
    assert post(client, '/v1/notifications/' + item['id'] + '/read', home[2]).status_code == 200
    async def maintain():
        async with factory() as db:
            await notifications.maintenance(db)
            await db.commit()
    asyncio.run(maintain())
    assert client.get('/v1/notifications', headers=home[2]).json()['items']
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM audit_log WHERE action='SIGNAL_CONTACT'")).scalar() == 1
        assert str(conn.execute(text('SELECT last_action_by FROM signal_event')).scalar()) == home[1]


@pytest.mark.parametrize('reason', ['revoke', 'expired', 'member', 'source'])
def test_signal_action_replay_revalidates_authorization(system, reason):
    client, engine, _, _ = system
    home, _, consent_id, events = setup_event(system)
    path = '/v1/signal-events/' + events[0]['signal_event_id'] + '/actions'
    body = {'action': 'ACKNOWLEDGE', 'expected_status': 'VALIDATED'}
    assert post(client, path, home[2], body, key='ack').status_code == 200
    if reason == 'revoke':
        assert post(client, '/v1/consents/' + consent_id + '/revoke', home[4]).status_code == 201
    else:
        with engine.begin() as conn:
            if reason == 'expired':
                conn.execute(text("UPDATE consent SET expires_at=now()-interval '1 second'"))
            elif reason == 'member':
                conn.execute(text("UPDATE family_member SET status='REVOKED' WHERE user_id=:id"), {'id': home[1]})
            else:
                conn.execute(text("UPDATE conversation SET deleted_at=now()"))
    assert post(client, path, home[2], body, key='ack').status_code == 404
    assert post(client, path, home[2], {'action': 'RESOLVE', 'expected_status': 'ACKNOWLEDGED'}).status_code == 404
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM signal_event')).scalar() == 'ACKNOWLEDGED'


@pytest.mark.parametrize('role', ['CAREGIVER', 'EMERGENCY_CONTACT'])
def test_signal_read_permission_does_not_grant_handling(system, role):
    client, engine, _, _ = system
    home, _, _, events = setup_event(system)
    path = '/v1/signal-events/' + events[0]['signal_event_id']
    body = {'action': 'ACKNOWLEDGE', 'expected_status': 'VALIDATED'}
    assert post(client, path + '/actions', home[4], body).status_code == 404
    outsider, outsider_headers = login(client, 'demo-other')
    assert post(client, path + '/actions', outsider_headers, body).status_code == 404
    other, headers = login(client, 'demo-caregiver')
    invitation = post(client, f'/v1/families/{home[0]}/invitations', home[2],
        {'target_role': role, 'expires_at': (utcnow()+timedelta(hours=1)).isoformat()}).json()['token']
    joined = post(client, f'/v1/family-invitations/{invitation}/accept', headers, {'confirm_identity': True}).json()
    consent = post(client, '/v1/consents', home[4], dict(family_id=home[0], subject_user_id=home[3],
        grantee_user_id=other, scope='NOTIFICATION_TO_FAMILY', source='SETTINGS'))
    assert consent.status_code == 201
    member_path = f'/v1/families/{home[0]}/members/{joined["id"]}'
    read_member = client.patch(member_path, headers={**home[2], 'If-Match': str(joined['version'])},
        json={'permission_codes': ['SIGNAL_READ']})
    assert read_member.status_code == 200
    assert client.get(path, headers=headers).json()['can_handle'] is False
    assert post(client, path + '/actions', headers, body, key='caregiver-ack').status_code == 403
    writer = client.patch(member_path, headers={**home[2], 'If-Match': str(read_member.json()['version'])},
        json={'permission_codes': ['SIGNAL_READ', 'SIGNAL_WRITE']})
    assert writer.status_code == 200
    assert post(client, path + '/actions', headers, body, key='caregiver-ack').status_code == 200
    removed = client.patch(member_path, headers={**home[2], 'If-Match': str(writer.json()['version'])},
        json={'permission_codes': ['SIGNAL_READ']})
    assert removed.status_code == 200
    assert post(client, path + '/actions', headers, body, key='caregiver-ack').status_code == 403


def test_signal_resolution_stops_pending_dispatch_and_rejects_skipped_confirmation(system):
    client, engine, factory, _ = system
    home, _, _, events = setup_event(system, channels=['IN_APP', 'PUSH'])
    path = '/v1/signal-events/' + events[0]['signal_event_id'] + '/actions'
    assert post(client, path, home[2], {'action': 'CONTACT', 'expected_status': 'VALIDATED'}).status_code == 409
    assert post(client, path, home[2], {'action': 'RESOLVE', 'expected_status': 'VALIDATED'}).status_code == 409
    assert post(client, path, home[2], {'action': 'ACKNOWLEDGE', 'expected_status': 'VALIDATED', 'owner_user_id': home[1]}).status_code == 422
    assert post(client, path, home[2], {'action': 'ACKNOWLEDGE', 'expected_status': 'VALIDATED'}).status_code == 200
    assert post(client, path, home[2], {'action': 'RESOLVE', 'expected_status': 'ACKNOWLEDGED'}).status_code == 200
    drain(factory)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM notification WHERE status <> 'CANCELLED'")).scalar() == 0
        assert conn.execute(text('SELECT status FROM signal_event')).scalar() == 'RESOLVED'


def test_false_positive_is_terminal_idempotent_and_cancels_queue(system):
    client, engine, factory, _ = system
    home, _, _, events = setup_event(system, channels=['IN_APP', 'PUSH', 'SMS', 'PHONE'])
    path = '/v1/signal-events/' + events[0]['signal_event_id']
    body = {'action': 'FALSE_POSITIVE', 'expected_status': 'VALIDATED'}
    response = post(client, path + '/actions', home[2], body, key='false-positive')
    assert response.status_code == 200
    assert response.json()['status'] == response.json()['resolution_code'] == 'FALSE_POSITIVE'
    assert [entry['action'] for entry in response.json()['history']] == ['FALSE_POSITIVE']
    assert post(client, path + '/actions', home[2], body, key='false-positive').status_code == 200
    assert post(client, path + '/actions', home[2], {'action': 'RESOLVE', 'expected_status': 'FALSE_POSITIVE'}).status_code == 409
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM notification WHERE status='CANCELLED'")).scalar() == 4
        assert conn.execute(text("SELECT count(*) FROM audit_log WHERE action='SIGNAL_FALSE_POSITIVE'")).scalar() == 1
    drain(factory)


def test_contacts_are_self_managed_encrypted_shared_with_handlers_and_deleted(system, monkeypatch):
    from cryptography.fernet import Fernet
    from app.platform.config import get_settings
    monkeypatch.setenv('CONTACT_ENCRYPTION_KEY', Fernet.generate_key().decode())
    get_settings.cache_clear()
    client, engine, _, _ = system
    home, _, _, events = setup_event(system)
    path = f'/v1/families/{home[0]}/my-contact'
    assert client.get(path, headers=home[4]).json()['version'] == 0
    body = dict(phone='+12025550101', share_phone=True, emergency=False, ntfy_topic='')
    saved = client.put(path, headers={**home[4], 'If-Match': '0'}, json=body)
    assert saved.status_code == 200
    assert client.put(path, headers={**home[4], 'If-Match': '0'}, json=body).status_code == 409
    with engine.connect() as conn:
        ciphertext = conn.execute(text('SELECT phone_ciphertext FROM family_contact')).scalar()
        assert '+12025550101' not in ciphertext
    event = '/v1/signal-events/' + events[0]['signal_event_id']
    assert client.get(event, headers=home[2]).json()['contacts'][0]['phone'] == '+12025550101'
    assert client.get(event, headers=home[4]).json().get('contacts') is None
    assert client.get(path, headers=home[2]).json()['phone'] == ''
    _, outsider = login(client, 'demo-other')
    assert client.get(path, headers=outsider).status_code == 404
    assert client.delete(path, headers=home[4]).status_code == 204
    assert client.get(event, headers=home[2]).json()['contacts'] == []
    assert client.put(path, headers={**home[4], 'If-Match': '0'}, json=body).status_code == 200
    members = client.get(f'/v1/families/{home[0]}/members', headers=home[2]).json()['items']
    elder = next(m for m in members if m['user_id'] == home[3])
    assert client.patch(f'/v1/families/{home[0]}/members/{elder["id"]}',
        headers={**home[2], 'If-Match': str(elder['version'])}, json={'status': 'REVOKED'}).status_code == 200
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM family_contact')).scalar() == 0


def test_external_disabled_fails_explicitly_without_sending(system):
    client, engine, factory, _ = system
    home, _, _, _ = setup_event(system, channels=['SMS', 'PHONE'])
    assert client.get('/v1/notification-capabilities', headers=home[2]).json()['external_enabled'] is False
    drain(factory)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status,error_code FROM notification ORDER BY channel')).all() == [
            ('FAILED', 'CHANNEL_NOT_CONFIGURED'), ('FAILED', 'CHANNEL_NOT_CONFIGURED')]


@pytest.mark.parametrize('outcome', ['accepted', 'timeout', 'crash'])
def test_external_delivery_persistence_receipts_and_no_duplicate_send(system, monkeypatch, outcome):
    from cryptography.fernet import Fernet
    from app.integrations.notifications import Receipt, DeliveryFailure
    from app.platform.config import get_settings, Settings
    from app.modules.notification.models import Notification
    monkeypatch.setenv('CONTACT_ENCRYPTION_KEY', Fernet.generate_key().decode())
    get_settings.cache_clear()
    config = Settings(app_env='dev', notification_external_enabled=True)
    monkeypatch.setattr(notifications, 'get_settings', lambda: config)
    sent = []
    class Provider:
        def __init__(self, settings):
            pass
        async def send(self, channel, destination):
            sent.append(channel)
            assert destination == '+12025550101'
            if outcome == 'timeout':
                raise DeliveryFailure('DELIVERY_UNKNOWN')
            return Receipt('twilio', ('SM' if channel == 'SMS' else 'CA') + 'a' * 32, 'queued')
        async def status(self, channel, identifier):
            return 'delivered' if channel == 'SMS' else 'completed'
    monkeypatch.setattr(notifications, 'ExternalNotifications', Provider)
    client, engine, factory, _ = system
    home, _, _, events = setup_event(system, channels=['SMS', 'PHONE'])
    path = f'/v1/families/{home[0]}/my-contact'
    assert client.put(path, headers={**home[2], 'If-Match': '0'}, json={'phone': '+12025550101'}).status_code == 200
    if outcome == 'crash':
        async def interrupted():
            async with factory() as db:
                task = await tasks.claim(db)
                await db.commit()
            async with factory() as db:
                await notifications.prepare(db, task.id, task.lease_token, task.resource_id)
                await db.commit()
        asyncio.run(interrupted())
        with engine.begin() as conn:
            conn.execute(text("UPDATE task_outbox SET lease_until=now()-interval '1 second' WHERE status='RUNNING'"))
    drain(factory)
    drain(factory)
    if outcome == 'accepted':
        async def maintain():
            async with factory() as db:
                for row in (await db.scalars(select(Notification))).all():
                    await notifications.refresh_receipt(db, row)
                await db.commit()
        asyncio.run(maintain())
        assert sorted(sent) == ['PHONE', 'SMS']
        with engine.connect() as conn:
            assert conn.execute(text('SELECT channel,status,provider_status FROM notification ORDER BY channel')).all() == [
                ('PHONE', 'SENT', 'completed'), ('SMS', 'DELIVERED', 'delivered')]
            assert conn.execute(text('SELECT status FROM signal_event')).scalar() == 'NOTIFIED'
    else:
        assert len(sent) == (1 if outcome == 'crash' else 2)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM notification WHERE error_code='DELIVERY_UNKNOWN'")).scalar() == (1 if outcome == 'crash' else 2)
