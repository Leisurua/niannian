import asyncio
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from niannian_elder_demo.api import ElderClient
from niannian_family_client.api import NianNianClient
from app.modules.auth.api import _attempts
from app.modules.auth.service import DEMO_USERS
from app.modules.auth.tokens import TokenCodec, digest
from app.modules.consent.service import require_scope
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow
from sqlalchemy import inspect, text

from backend.tests.support import KEY, URL

pytestmark = pytest.mark.skipif(not URL, reason='Set TEST_DATABASE_URL to run PostgreSQL integration tests')


def login(client, name, device='fictional-device'):
    response = client.post('/v1/auth/login', json={'credential': {'type':'DEMO','identifier': name},
                'device':{'device_id':device,'name':'演示设备','app_version':'0.1.0'}})
    assert response.status_code == 201
    result = response.json()
    return result, {'Authorization':'Bearer '+result['access_token']}


def post(client, url, headers, body, key=None):
    return client.post(url, headers={**headers, 'Idempotency-Key':key or str(uuid4())}, json=body)


def family_with_elder(client):
    child, ch = login(client, 'demo-child')
    elder, eh = login(client, 'demo-elder')
    family = post(client, '/v1/families', ch, {'name':'演示家庭甲'}).json()
    invitation = post(client, f"/v1/families/{family['id']}/invitations", ch,
                      {'target_role':'ELDER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()
    member = post(client, f"/v1/family-invitations/{invitation['token']}/accept", eh, {'confirm_identity':True})
    assert member.status_code == 200 and member.json()['status'] == 'ACTIVE'
    return family, child, ch, elder, eh, member.json()


def test_login_refresh_reuse_revokes_only_current_user(system):
    client, engine, _, _ = system
    first, first_headers = login(client, 'demo-child', 'device-one')
    second, second_headers = login(client, 'demo-child', 'device-two')
    other, other_headers = login(client, 'demo-other')
    rotated = client.post('/v1/auth/refresh', json={'refresh_token':first['refresh_token']})
    assert rotated.status_code == 200
    assert client.get('/v1/me', headers=first_headers).status_code == 401
    replacement = rotated.json()
    reuse = client.post('/v1/auth/refresh', json={'refresh_token':first['refresh_token']})
    assert reuse.status_code == 401 and reuse.json()['error']['code'] == 'AUTH_REFRESH_REUSED'
    assert client.get('/v1/me', headers={'Authorization':'Bearer '+replacement['access_token']}).status_code == 401
    assert client.get('/v1/me', headers=second_headers).status_code == 401
    assert client.get('/v1/me', headers=other_headers).status_code == 200
    with engine.connect() as connection:
        stored = connection.execute(text('SELECT refresh_token_hash FROM device_session')).scalars().all()
        assert all(len(value)==64 for value in stored)
        assert digest(first['refresh_token']) in stored
        assert connection.execute(text("SELECT count(*) FROM audit_log WHERE action='AUTH_REFRESH_REUSED'")).scalar() == 1


def test_logout_and_logout_all(system):
    client, _, _, _ = system
    a, ah = login(client, 'demo-child', 'a')
    b, bh = login(client, 'demo-child', 'b')
    assert client.post('/v1/auth/logout', headers=ah).status_code == 204
    assert client.get('/v1/me', headers=ah).status_code == 401
    assert client.post('/v1/auth/refresh', json={'refresh_token':a['refresh_token']}).status_code == 401
    assert client.get('/v1/me', headers=bh).status_code == 200
    assert client.post('/v1/auth/logout-all', headers=bh).status_code == 204
    assert client.get('/v1/me', headers=bh).status_code == 401
    assert client.post('/v1/auth/refresh', json={'refresh_token':b['refresh_token']}).status_code == 401


def test_family_idempotency_scope_and_pending_confirmation(system):
    client, engine, _, _ = system
    _, child = login(client, 'demo-child')
    _, elder = login(client, 'demo-elder')
    _, other = login(client, 'demo-other')
    first = post(client, '/v1/families', child, {'name':'演示家庭甲'}, 'same-create')
    repeat = post(client, '/v1/families', child, {'name':'演示家庭甲'}, 'same-create')
    assert first.status_code == repeat.status_code == 201
    fid = first.json()['id']
    assert repeat.json()['id'] == fid
    assert post(client, '/v1/families', child, {'name':'演示家庭乙'}, 'same-create').status_code == 409
    assert client.get('/v1/families/'+fid, headers=other).status_code == 404
    assert client.get('/v1/families', headers=other).json()['items'] == []
    invitation = post(client, f'/v1/families/{fid}/invitations', child,
        {'target_role':'ELDER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()})
    path = '/v1/family-invitations/'+invitation.json()['token']+'/accept'
    pending = post(client, path, elder, {})
    assert pending.status_code == 200 and pending.json()['status'] == 'PENDING'
    assert client.get('/v1/families/'+fid, headers=elder).status_code == 404
    assert client.get('/v1/families', headers=elder).json()['items'][0]['member_status'] == 'PENDING'
    forced = client.patch(f"/v1/families/{fid}/members/{pending.json()['id']}",
                          headers={**child,'If-Match':str(pending.json()['version'])}, json={'status':'ACTIVE'})
    assert forced.status_code == 409
    assert post(client, path, other, {'confirm_identity':True}).status_code == 404
    active = post(client, path, elder, {'confirm_identity':True})
    assert active.status_code == 200 and active.json()['status'] == 'ACTIVE'
    assert client.get('/v1/families/'+fid, headers=elder).status_code == 200
    assert post(client, path, elder, {'confirm_identity':True}).status_code == 404
    with engine.connect() as connection:
        assert connection.execute(text('SELECT used_count FROM family_invitation')).scalar() == 1


def test_consent_is_subject_owned_immutable_and_immediately_revoked(system):
    client, engine, factory, _ = system
    fam, child, ch, elder, eh, _ = family_with_elder(client)
    data = {'family_id':fam['id'],'subject_user_id':elder['user']['id'],'grantee_user_id':child['user']['id'],
            'scope':'FAMILY_MEMORY','source':'SETTINGS'}
    assert post(client, '/v1/consents', ch, data).status_code == 403
    granted = post(client, '/v1/consents', eh, data, 'grant-one')
    assert granted.status_code == 201
    assert post(client, '/v1/consents', eh, data, 'grant-one').json()['id'] == granted.json()['id']
    async def check_allowed(expected):
        async with factory() as db:
            if expected:
                await require_scope(db, UUID(fam['id']), UUID(elder['user']['id']), UUID(child['user']['id']), 'FAMILY_MEMORY')
            else:
                with pytest.raises(AppError) as denied:
                    await require_scope(db, UUID(fam['id']), UUID(elder['user']['id']), UUID(child['user']['id']), 'FAMILY_MEMORY')
                assert denied.value.code == 'PERMISSION_CONSENT_REQUIRED'
    asyncio.run(check_allowed(True))
    assert post(client, '/v1/consents/'+granted.json()['id']+'/revoke', ch, {}).status_code == 403
    revoked = post(client, '/v1/consents/'+granted.json()['id']+'/revoke', eh, {}, 'revoke-one')
    assert revoked.status_code == 201 and revoked.json()['status'] == 'REVOKED'
    assert post(client, '/v1/consents/'+granted.json()['id']+'/revoke', eh, {}, 'revoke-one').json()['id'] == revoked.json()['id']
    asyncio.run(check_allowed(False))
    _, outside = login(client, 'demo-other')
    assert client.get('/v1/consents?subject_user_id='+elder['user']['id'], headers=outside).json()['items'] == []
    assert client.get('/v1/consents/'+granted.json()['id'], headers=outside).status_code == 404
    with engine.connect() as connection:
        assert connection.execute(text('SELECT status FROM consent ORDER BY created_at')).scalars().all() == ['GRANTED','REVOKED']
        assert connection.execute(text("SELECT count(*) FROM audit_log WHERE action IN ('CONSENT_GRANTED','CONSENT_REVOKED')")).scalar() == 2


def test_member_permissions_mass_assignment_and_optimistic_concurrency(system):
    client, _, _, _ = system
    fam, _, ch, _, eh, member = family_with_elder(client)
    path = f"/v1/families/{fam['id']}/members/{member['id']}"
    assert client.get(f"/v1/families/{fam['id']}/members", headers=eh).status_code == 403
    assert client.patch(path, headers={**eh,'If-Match':str(member['version'])}, json={'permission_codes':['MEMBER_ADMIN']}).status_code == 403
    assert client.patch(path, headers={**ch,'If-Match':str(member['version'])}, json={'role':'SYSTEM'}).status_code == 422
    assert client.patch(path, headers={**ch,'If-Match':str(member['version'])}, json={'owner_user_id':str(uuid4())}).status_code == 422
    changed = client.patch(path, headers={**ch,'If-Match':str(member['version'])}, json={'permission_codes':['MEMBER_READ']})
    assert changed.status_code == 200 and changed.json()['version'] != member['version']
    assert client.patch(path, headers={**ch,'If-Match':str(member['version'])}, json={'role':'CAREGIVER'}).status_code == 409
    assert client.get(f"/v1/families/{fam['id']}/members", headers=eh).status_code == 200
    assert client.post(path+'/leave', headers=eh).status_code == 204
    assert client.get('/v1/families/'+fam['id'], headers=eh).status_code == 404


def test_invitation_expiry_revoke_and_concurrent_use(system):
    client, engine, _, _ = system
    _, ch = login(client, 'demo-child')
    _, eh = login(client, 'demo-elder')
    _, oh = login(client, 'demo-other')
    fid = post(client,'/v1/families',ch,{'name':'并发演示家庭'}).json()['id']
    invitation = post(client,f'/v1/families/{fid}/invitations',ch,
                       {'target_role':'ELDER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()
    path='/v1/family-invitations/'+invitation['token']+'/accept'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda header: post(client,path,header,{'confirm_identity':True}).status_code,[eh,oh]))
    assert sorted(results)==[200,404]
    with engine.connect() as connection:
        assert connection.execute(text('SELECT used_count FROM family_invitation')).scalar()==1
    invitation2=post(client,f'/v1/families/{fid}/invitations',ch,
                       {'target_role':'ELDER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()
    assert client.post(f"/v1/families/{fid}/invitations/{invitation2['id']}/revoke",headers=ch).status_code==204
    assert post(client,'/v1/family-invitations/'+invitation2['token']+'/accept',eh,{'confirm_identity':True}).status_code==404
    expired=post(client,f'/v1/families/{fid}/invitations',ch,
                 {'target_role':'CAREGIVER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()
    with engine.begin() as connection:
        connection.execute(text("UPDATE family_invitation SET created_at=now()-interval '2 hours', expires_at=now()-interval '1 hour' WHERE id=:id"), {'id':expired['id']})
    assert post(client,'/v1/family-invitations/'+expired['token']+'/accept',eh,{'confirm_identity':True}).status_code==404


def test_admin_can_revoke_expired_pending_membership_without_activating(system):
    client, _, _, _=system
    _, ch=login(client,'demo-child');_, eh=login(client,'demo-elder')
    fid=post(client,'/v1/families',ch,{'name':'待确认演示家庭'}).json()['id']
    invite=post(client,f'/v1/families/{fid}/invitations',ch,
                {'target_role':'ELDER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()
    pending=post(client,'/v1/family-invitations/'+invite['token']+'/accept',eh,{}).json()
    path=f"/v1/families/{fid}/members/{pending['id']}"
    assert client.patch(path,headers={**ch,'If-Match':str(pending['version'])},json={'status':'REVOKED'}).status_code==200
    assert post(client,'/v1/family-invitations/'+invite['token']+'/accept',eh,{'confirm_identity':True}).status_code==404
    replacement=post(client,f'/v1/families/{fid}/invitations',ch,
                {'target_role':'ELDER','expires_at':(utcnow()+timedelta(hours=1)).isoformat()}).json()
    assert post(client,'/v1/family-invitations/'+replacement['token']+'/accept',eh,{'confirm_identity':True}).status_code==200


def test_cursor_is_bound_to_user_and_filter(system):
    client, _, _, _=system
    _, a=login(client,'demo-child');_, b=login(client,'demo-other')
    for index in range(3): post(client,'/v1/families',a,{'name':f'分页演示 {index}'})
    first=client.get('/v1/families?limit=2',headers=a).json()
    assert len(first['items'])==2 and first['page']['has_more'] is True
    cursor=first['page']['next_cursor']
    second=client.get('/v1/families',params={'limit':2,'cursor':cursor},headers=a).json()
    assert len(second['items'])==1 and second['page']['has_more'] is False
    assert client.get('/v1/families',params={'cursor':cursor},headers=b).status_code==400
    assert client.get('/v1/families?cursor=malformed',headers=a).status_code==400


def test_expired_and_wrong_identity_access_are_rejected(system):
    client, _, _, _=system
    a, _=login(client,'demo-child');login(client,'demo-other')
    codec=TokenCodec(KEY)
    expired=codec.access(UUID(a['user']['id']),UUID(a['device_session']['id']),'演示设备',utcnow()-timedelta(hours=1))
    assert client.get('/v1/me',headers={'Authorization':'Bearer '+expired}).status_code==401
    wrong=codec.access(DEMO_USERS['demo-other'][0],UUID(a['device_session']['id']),'演示设备')
    assert client.get('/v1/me',headers={'Authorization':'Bearer '+wrong}).status_code==401


def test_database_constraints_exist(system):
    _, engine, _, _=system
    schema=inspect(engine)
    assert {'alembic_version', 'consent', 'family_member', 'device_session'} <= set(schema.get_table_names())
    assert any(index['name']=='uq_member_current' and index['unique'] for index in schema.get_indexes('family_member'))
    assert any(check['name']=='ck_invitation_usage' for check in schema.get_check_constraints('family_invitation'))
    assert any(check['name']=='ck_consent_revoked' for check in schema.get_check_constraints('consent'))


def test_refresh_concurrency_detects_reuse_and_revokes_replacement(system):
    client, engine, _, _ = system
    session, _ = login(client, 'demo-child')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/v1/auth/refresh',
            json={'refresh_token': session['refresh_token']}), range(2)))
    assert sorted(response.status_code for response in results) == [200, 401]
    replacement = next(response.json() for response in results if response.status_code == 200)
    assert client.get('/v1/me', headers={'Authorization': 'Bearer ' + replacement['access_token']}).status_code == 401
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM device_session WHERE revoked_at IS NULL')).scalar() == 0


def test_scope_expiry_grantee_and_membership_are_checked_on_each_decision(system):
    client, engine, factory, _ = system
    fam, child, ch, elder, eh, member = family_with_elder(client)
    third, th = login(client, 'demo-caregiver')
    invite = post(client, f"/v1/families/{fam['id']}/invitations", ch,
        {'target_role': 'CAREGIVER', 'expires_at': (utcnow() + timedelta(hours=1)).isoformat()}).json()
    assert post(client, '/v1/family-invitations/' + invite['token'] + '/accept', th, {'confirm_identity': True}).status_code == 200
    granted = post(client, '/v1/consents', eh, {'family_id': fam['id'], 'subject_user_id': elder['user']['id'],
        'grantee_user_id': child['user']['id'], 'scope': 'FAMILY_MEMORY', 'source': 'SETTINGS',
        'expires_at': (utcnow() + timedelta(hours=1)).isoformat()}).json()

    async def decision(grantee, scope, allowed=False):
        async with factory() as db:
            if allowed:
                await require_scope(db, UUID(fam['id']), UUID(elder['user']['id']), UUID(grantee), scope)
            else:
                with pytest.raises(AppError):
                    await require_scope(db, UUID(fam['id']), UUID(elder['user']['id']), UUID(grantee), scope)
    asyncio.run(decision(child['user']['id'], 'FAMILY_MEMORY', True))
    asyncio.run(decision(third['user']['id'], 'FAMILY_MEMORY'))
    asyncio.run(decision(child['user']['id'], 'HEALTH_MEDICATION'))
    with engine.begin() as connection:
        connection.execute(text("UPDATE consent SET expires_at=now()-interval '1 second' WHERE id=:id"), {'id': granted['id']})
    asyncio.run(decision(child['user']['id'], 'FAMILY_MEMORY'))
    assert post(client, '/v1/consents', eh, {'family_id': fam['id'], 'subject_user_id': elder['user']['id'],
        'grantee_user_id': child['user']['id'], 'scope': 'FAMILY_MEMORY', 'source': 'SETTINGS'}).status_code == 201
    assert client.patch(f"/v1/families/{fam['id']}/members/{member['id']}", headers={**ch, 'If-Match': str(member['version'])},
        json={'status': 'REVOKED'}).status_code == 200
    asyncio.run(decision(child['user']['id'], 'FAMILY_MEMORY'))
    assert client.get('/v1/consents/' + granted['id'], headers=eh).status_code == 404


def test_consent_cross_family_and_invitation_do_not_grant_data_access(system):
    client, _, factory, _ = system
    fam, child, ch, elder, eh, _ = family_with_elder(client)
    _, outside = login(client, 'demo-other')
    another = post(client, '/v1/families', outside, {'name': '另一演示家庭'}).json()
    body = {'family_id': another['id'], 'subject_user_id': elder['user']['id'],
        'grantee_user_id': child['user']['id'], 'scope': 'FAMILY_MEMORY', 'source': 'SETTINGS'}
    assert post(client, '/v1/consents', eh, body).status_code == 404
    assert client.get(f"/v1/families/{fam['id']}/members", headers=outside).status_code == 404

    async def no_implicit_consent():
        async with factory() as db:
            with pytest.raises(AppError) as denied:
                await require_scope(db, UUID(fam['id']), UUID(elder['user']['id']), UUID(child['user']['id']), 'FAMILY_MEMORY')
            assert denied.value.code == 'PERMISSION_CONSENT_REQUIRED'
    asyncio.run(no_implicit_consent())


def test_demo_allowlist_rate_limit_and_suspended_identity(system, monkeypatch):
    client, engine, _, _ = system
    payload = {'credential': {'type': 'DEMO', 'identifier': 'not-a-demo-user'},
        'device': {'device_id': 'fictional-device', 'name': '演示设备', 'app_version': '0.1.0'}}
    assert client.post('/v1/auth/login', json=payload).status_code == 401
    payload['credential'] = {'type': 'VERIFICATION_CODE', 'identifier': 'demo-child', 'proof': 'fictional-proof'}
    assert client.post('/v1/auth/login', json=payload).status_code == 401
    session, headers = login(client, 'demo-child')
    with engine.begin() as connection:
        connection.execute(text('UPDATE "user" SET global_status=\'SUSPENDED\' WHERE id=:id'), {'id': session['user']['id']})
    assert client.get('/v1/me', headers=headers).status_code == 401
    assert client.post('/v1/auth/refresh', json={'refresh_token': session['refresh_token']}).status_code == 401
    monkeypatch.setenv('AUTH_LOGIN_LIMIT', '1')
    get_settings.cache_clear()
    _attempts.clear()
    payload['credential'] = {'type': 'DEMO', 'identifier': 'not-a-demo-user'}
    assert client.post('/v1/auth/login', json=payload).status_code == 401
    assert client.post('/v1/auth/login', json=payload).status_code == 429


def test_live_api_login_family_consent_slice_uses_portable_entrypoint(system):
    root = Path(__file__).resolve().parents[3]
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    environment = {**os.environ, 'DATABASE_URL': URL, 'PYTHONPATH': str(root / 'backend'), 'PYTHONUTF8': '1'}
    process = subprocess.Popen([sys.executable, '-m', 'app', '--port', str(port)], cwd=root,
        env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5) as client:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, 'API exited before readiness'
                try:
                    if client.get('/health').status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline, 'API readiness timeout'
                time.sleep(.05)
            family_app = NianNianClient(str(client.base_url))
            elder_app = ElderClient(str(client.base_url))
            child, elder = family_app.login(), elder_app.login()
            ch = {'Authorization': 'Bearer ' + family_app.access_token}
            eh = {'Authorization': 'Bearer ' + elder_app.access_token}
            fam = family_app.create_family('虚构 Windows 联调家庭')
            invite = family_app.create_invitation(fam['id'])
            assert elder_app.accept_invitation(invite['token'])['status'] == 'ACTIVE'
            assert elder_app.list_families()[0]['id'] == fam['id']
            assert family_app.backend_features() == {'devices': True, 'messages': True}
            family_app.register_family_device(fam['id'])
            elder_app.register_device(fam['id'])
            sent = family_app.send_text_to_role('虚构 HTTP 留言')
            inbox = elder_app.receive_messages()
            assert inbox[0]['id'] == sent['id']
            delivery_id = inbox[0]['deliveries'][0]['id']
            elder_app.acknowledge(delivery_id, 'read')
            assert family_app.message(sent['id'])['deliveries'][0]['status'] == 'READ'
            # Android shares these HTTP request bodies and the cursor contract.
            reply = post(client, '/v1/messages', eh, {'family_id': fam['id'], 'message_type': 'TEXT',
                'destination': {'type': 'FAMILY_ROLE', 'role': 'CHILD'}, 'payload': {'text': '虚构 Android 回复'}})
            assert reply.status_code == 201
            assert family_app.receive_messages()[0]['payload']['text'] == '虚构 Android 回复'
            body = {'family_id': fam['id'], 'subject_user_id': elder['user']['id'],
                'grantee_user_id': child['user']['id'], 'scope': 'FAMILY_MEMORY', 'source': 'SETTINGS'}
            granted = post(client, '/v1/consents', eh, body)
            assert granted.status_code == 201
            revoked = post(client, '/v1/consents/' + granted.json()['id'] + '/revoke', eh, {})
            assert revoked.status_code == 201 and revoked.json()['status'] == 'REVOKED'
            rows = client.get('/v1/consents', headers=ch, params={'family_id': fam['id']}).json()['items']
            assert [row['status'] for row in rows] == ['REVOKED', 'GRANTED']
            assert client.post('/v1/auth/logout-all', headers=eh).status_code == 204
            assert client.get('/v1/me', headers=eh).status_code == 401
            family_app.logout()
            assert client.get('/v1/messages', headers=ch).status_code == 401
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
