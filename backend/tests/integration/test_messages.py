import io
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.error import HTTPError
from uuid import uuid4

from sqlalchemy import text

from backend.tests.support import household, login, post, utcnow


def register(client, headers, family, elder=False, device=None):
    return post(client, '/v1/devices/register', headers, dict(device_id=device or str(uuid4()), family_id=family,
        device_type='ANDROID_TABLET' if elder else 'OTHER', client_kind='ELDER_MOBILE' if elder else 'FAMILY_MOBILE',
        app_version='0.1.0', os_version='fictional', capabilities={'rest_polling': True}))


def body(family, role='ELDER', content='虚构的家人留言'):
    return dict(family_id=family, message_type='TEXT', destination={'type': 'FAMILY_ROLE', 'role': role},
                payload={'text': content}, priority='NORMAL')


def test_offline_member_receives_after_registering_and_receipts_survive_new_device(system):
    client, engine, *_ = system
    fid, child, ch, elder, eh = household(client)
    assert register(client, ch, fid).status_code == 201
    sent = post(client, '/v1/messages', ch, body(fid), key='send-once')
    assert sent.status_code == 201, sent.text
    message = sent.json()
    assert message['deliveries'][0]['status'] == 'QUEUED'
    assert post(client, '/v1/messages', ch, body(fid), key='send-once').json()['id'] == message['id']
    assert post(client, '/v1/messages', ch, body(fid, content='changed'), key='send-once').status_code == 409
    assert register(client, eh, fid, True).status_code == 201
    inbox = client.get('/v1/messages?box=INBOX', headers=eh).json()['items']
    assert [row['id'] for row in inbox] == [message['id']]
    delivery = inbox[0]['deliveries'][0]['id']
    assert post(client, f'/v1/message-deliveries/{delivery}/read', ch).status_code == 404
    for invalid_key in ('', 'x' * 129):
        invalid = client.post(f'/v1/message-deliveries/{delivery}/received',
                              headers={**eh, 'Idempotency-Key': invalid_key}, json={})
        assert invalid.status_code == 422
    received = post(client, f'/v1/message-deliveries/{delivery}/received', eh).json()
    read = post(client, f'/v1/message-deliveries/{delivery}/read', eh).json()
    assert read['status'] == 'READ' and read['received_at'] == received['received_at']
    repeated = post(client, f'/v1/message-deliveries/{delivery}/received', eh).json()
    assert repeated['status'] == 'READ' and repeated['read_at'] == read['read_at']
    _, new_eh = login(client, 'demo-elder')
    assert register(client, new_eh, fid, True).status_code == 201
    assert client.get('/v1/messages', headers=new_eh).json()['items'][0]['deliveries'][0]['status'] == 'READ'
    reply = post(client, '/v1/messages', new_eh, body(fid, 'CHILD', '虚构回复'))
    assert reply.status_code == 201, reply.text
    assert client.get('/v1/messages?box=INBOX', headers=ch).json()['items'][0]['id'] == reply.json()['id']
    assert client.get('/v1/messages/' + message['id'], headers=ch).json()['deliveries'][0]['status'] == 'READ'
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM family_message')) == 2
        assert conn.scalar(text("SELECT count(*) FROM audit_log WHERE action = 'MESSAGE_READ'")) == 1
        assert '虚构的家人留言' not in str(conn.execute(text('SELECT metadata_redacted FROM audit_log')).all())


def test_device_and_message_family_isolation_roles_and_revocation(system):
    client, *_ = system
    fid, _, ch, _, eh = household(client)
    register(client, ch, fid, device='fictional-fixed-device')
    first = register(client, ch, fid, device='fictional-fixed-device').json()
    assert len(client.get('/v1/devices', headers=ch).json()['items']) == 1
    assert first['client_kind'] == 'FAMILY_MOBILE'
    assert register(client, eh, fid).status_code == 403
    assert register(client, eh, fid, True, device='fictional-fixed-device').status_code == 409
    register(client, eh, fid, True)
    message = post(client, '/v1/messages', ch, body(fid)).json()
    _, other = login(client, 'demo-other')
    other_fid = post(client, '/v1/families', other, {'name': '另一个虚构家庭'}).json()['id']
    register(client, other, other_fid)
    assert register(client, other, fid).status_code == 404
    assert client.get('/v1/devices?family_id=' + fid, headers=other).status_code == 404
    assert client.get('/v1/messages/' + message['id'], headers=other).status_code == 404
    assert post(client, '/v1/messages', other, body(fid)).status_code == 409
    assert post(client, '/v1/messages', other, body(other_fid)).status_code == 409
    assert post(client, '/v1/message-deliveries/' + message['deliveries'][0]['id'] + '/read', other).status_code == 404
    member = next(row for row in client.get('/v1/families/' + fid + '/members', headers=ch).json()['items'] if row['role'] == 'ELDER')
    assert client.patch(f'/v1/families/{fid}/members/{member["id"]}', headers={**ch, 'If-Match': str(member['version'])},
                        json={'status': 'REVOKED'}).status_code == 200
    assert client.get('/v1/messages', headers=eh).status_code == 404
    assert post(client, '/v1/message-deliveries/' + message['deliveries'][0]['id'] + '/read', eh).status_code == 404
    assert all(row['owner_user_id'] != member['user_id'] for row in client.get('/v1/devices', headers=ch).json()['items'])


def test_paging_binding_scope_and_validation(system):
    client, *_ = system
    fid, _, ch, _, eh = household(client)
    assert post(client, '/v1/messages', ch, body(fid)).status_code == 409
    register(client, ch, fid)
    register(client, eh, fid, True)
    for content in ('', ' ', 'x' * 2001):
        assert post(client, '/v1/messages', ch, body(fid, content=content)).status_code == 422
    sent = [post(client, '/v1/messages', ch, body(fid, content=str(i))).json() for i in range(3)]
    for headers, box in ((ch, 'OUTBOX'), (eh, 'INBOX')):
        first = client.get(f'/v1/messages?box={box}&limit=2', headers=headers).json()
        assert first['page']['has_more']
        cursor = first['page']['next_cursor']
        second = client.get(f'/v1/messages?box={box}&after_sequence={cursor}', headers=headers).json()
        android = client.get(f'/v1/messages?box={box}&cursor={cursor}', headers=headers).json()
        assert [row['id'] for row in first['items'] + second['items']] == [row['id'] for row in sent]
        assert android['items'] == second['items'] and not second['page']['has_more']
    other_fid = post(client, '/v1/families', ch, {'name': '另一个虚构家庭'}).json()['id']
    register(client, ch, other_fid)
    assert client.get('/v1/messages?box=OUTBOX', headers=ch).json()['items'] == []
    assert client.get(f'/v1/messages?family_id={fid}', headers=ch).status_code == 409


def test_windows_clients_use_main_backend_with_android_receipts_refresh_and_logout(system, monkeypatch):
    from niannian_desktop import api
    from niannian_family_client.api import NianNianClient
    from niannian_elder_demo.api import ElderClient
    from app.modules.auth.service import codec
    from app.platform.config import get_settings
    from uuid import UUID
    client, *_ = system

    def transport(request, timeout):
        response = client.request(request.method, request.selector, content=request.data, headers=dict(request.header_items()))
        if response.status_code >= 400:
            raise HTTPError(request.full_url, response.status_code, 'API error', response.headers, io.BytesIO(response.content))
        return io.BytesIO(response.content)

    monkeypatch.setattr(api, 'urlopen', transport)
    family = NianNianClient('http://testserver')
    login_result = family.login()
    assert family.backend_features() == {'devices': True, 'messages': True}
    fid = family.create_family('虚构跨设备家庭')['id']
    token = family.create_invitation(fid)['token']
    elder = ElderClient('http://testserver')
    elder.login(); elder.accept_invitation(token)
    family.register_family_device(fid)
    elder.register_device(fid)
    family.send_text_to_role('Windows 发给 Android 的虚构留言')
    android_headers = {'Authorization': 'Bearer ' + elder.access_token}
    row = client.get(f'/v1/messages?family_id={fid}&box=INBOX&limit=100', headers=android_headers).json()['items'][0]
    post(client, f'/v1/message-deliveries/{row["deliveries"][0]["id"]}/read', android_headers)
    assert family.list_messages('OUTBOX')[0]['deliveries'][0]['status'] == 'READ'
    post(client, '/v1/messages', android_headers, body(fid, 'CHILD', 'Android 的虚构回复'))
    assert family.receive_messages()[0]['payload']['text'] == 'Android 的虚构回复'
    claims = codec(get_settings()).verify(family.access_token)
    family.access_token = codec(get_settings()).access(UUID(claims['sub']), UUID(claims['sid']), claims['dn'], utcnow() - timedelta(hours=1))
    family.list_messages('OUTBOX')
    assert family.refresh_token != login_result['refresh_token']
    access = family.access_token
    family.logout()
    assert family.access_token is None and family.binding is None
    assert client.get('/v1/messages', headers={'Authorization': 'Bearer ' + access}).status_code == 401


def test_simultaneous_opposite_sends_and_duplicate_submission(system, monkeypatch):
    from app.modules.family import service as family
    client, engine, *_ = system
    fid, _, ch, _, eh = household(client)
    register(client, ch, fid); register(client, eh, fid, True)
    original = family.context
    barrier = threading.Barrier(2)

    async def synchronized_context(*args, **kwargs):
        await asyncio.to_thread(barrier.wait, 5)
        return await original(*args, **kwargs)

    monkeypatch.setattr(family, 'context', synchronized_context)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post, client, '/v1/messages', headers, body(fid, role))
                   for headers, role in ((ch, 'ELDER'), (eh, 'CHILD'))]
        replies = [future.result(timeout=15) for future in futures]
    assert [r.status_code for r in replies] == [201, 201]
    monkeypatch.setattr(family, 'context', original)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post, client, '/v1/messages', ch, body(fid), 'same-request') for _ in range(2)]
        replies = [future.result(timeout=15) for future in futures]
    assert [r.status_code for r in replies] == [201, 201]
    assert replies[0].json()['id'] == replies[1].json()['id']
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM family_message')) == 3


def test_pending_nonrecipient_and_rejoined_member_cannot_read_old_inbox(system):
    client, *_ = system
    fid, _, ch, _, eh = household(client)
    register(client, ch, fid); register(client, eh, fid, True)
    message = post(client, '/v1/messages', ch, body(fid)).json()
    _, outsider = login(client, 'demo-other')
    invite = post(client, f'/v1/families/{fid}/invitations', ch,
        {'target_role': 'CHILD', 'expires_at': (utcnow() + timedelta(hours=1)).isoformat()}).json()['token']
    assert post(client, f'/v1/family-invitations/{invite}/accept', outsider).status_code == 200
    assert register(client, outsider, fid).status_code == 404
    post(client, f'/v1/family-invitations/{invite}/accept', outsider, {'confirm_identity': True})
    register(client, outsider, fid)
    assert client.get('/v1/messages/' + message['id'], headers=outsider).status_code == 404
    member = next(r for r in client.get(f'/v1/families/{fid}/members', headers=ch).json()['items'] if r['role'] == 'ELDER')
    post(client, f'/v1/families/{fid}/members/{member["id"]}/leave', eh)
    invite = post(client, f'/v1/families/{fid}/invitations', ch,
        {'target_role': 'ELDER', 'expires_at': (utcnow() + timedelta(hours=1)).isoformat()}).json()['token']
    post(client, f'/v1/family-invitations/{invite}/accept', eh, {'confirm_identity': True})
    register(client, eh, fid, True)
    assert client.get('/v1/messages', headers=eh).json()['items'] == []
    assert client.get('/v1/messages/' + message['id'], headers=eh).status_code == 404
    assert post(client, f'/v1/message-deliveries/{message["deliveries"][0]["id"]}/read', eh).status_code == 404
