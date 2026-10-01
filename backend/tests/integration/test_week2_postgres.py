import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.modules.auth.api import _attempts
from app.modules.auth.service import DEMO_USERS
from app.modules.auth.tokens import TokenCodec, digest
from app.modules.consent.service import require_scope
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow

KEY = 'fictional-week2-signing-key-' * 3
URL = os.environ.get('WEEK2_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Disposable PostgreSQL required; set WEEK2_TEST_DATABASE_URL')
TABLES = ['consent','family_member','family_invitation','device_session','audit_log','family','device_binding','user']


@pytest.fixture
def system(monkeypatch):
    if not make_url(URL).database.endswith('_week2_test'):
        pytest.fail('Refusing to reset a database without the _week2_test suffix')
    monkeypatch.setenv('AUTH_SIGNING_KEY', KEY)
    monkeypatch.setenv('AUTH_LOGIN_LIMIT', '1000')
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('PROVIDER_MODE', 'mock')
    get_settings.cache_clear()
    _attempts.clear()
    sync = create_engine(URL)
    with sync.begin() as connection:
        connection.execute(text('TRUNCATE ' + ','.join('"'+table+'"' for table in TABLES) + ' CASCADE'))
    async_engine = create_async_engine(URL, poolclass=NullPool)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    app.state.session_factory = factory
    with TestClient(app) as client:
        yield client, sync, factory
    del app.state.session_factory
    asyncio.run(async_engine.dispose())
    sync.dispose()
    _attempts.clear()
    get_settings.cache_clear()


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
    client, engine, _ = system
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
    client, _, _ = system
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
    client, engine, _ = system
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
    client, engine, factory = system
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
    client, _, _ = system
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
    client, engine, _ = system
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


def test_cursor_is_bound_to_user_and_filter(system):
    client, _, _=system
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
    client, _, _=system
    a, _=login(client,'demo-child');login(client,'demo-other')
    codec=TokenCodec(KEY)
    expired=codec.access(UUID(a['user']['id']),UUID(a['device_session']['id']),'演示设备',utcnow()-timedelta(hours=1))
    assert client.get('/v1/me',headers={'Authorization':'Bearer '+expired}).status_code==401
    wrong=codec.access(DEMO_USERS['demo-other'][0],UUID(a['device_session']['id']),'演示设备')
    assert client.get('/v1/me',headers={'Authorization':'Bearer '+wrong}).status_code==401


def test_database_constraints_exist(system):
    _, engine, _=system
    schema=inspect(engine)
    assert {'alembic_version', *TABLES} <= set(schema.get_table_names())
    assert any(index['name']=='uq_member_current' and index['unique'] for index in schema.get_indexes('family_member'))
    assert any(check['name']=='ck_invitation_usage' for check in schema.get_check_constraints('family_invitation'))
    assert any(check['name']=='ck_consent_revoked' for check in schema.get_check_constraints('consent'))
