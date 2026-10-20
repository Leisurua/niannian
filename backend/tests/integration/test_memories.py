from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from app.platform.identifiers import utcnow
from sqlalchemy import text

from backend.tests.support import URL, grant, household, login, memory, post

pytestmark = pytest.mark.skipif(not URL, reason='Set TEST_DATABASE_URL to run PostgreSQL integration tests')

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


def test_memory_id_enumeration_errors_are_identical(system):
    client, _, _, _ = system
    home = household(client); grant(client, home)
    item = memory(client, home)
    _, outsider = login(client, 'demo-other')
    known = client.get('/v1/memories/'+item['id'], headers=outsider)
    unknown = client.get('/v1/memories/'+str(uuid4()), headers=outsider)
    assert known.status_code == unknown.status_code == 404
    assert known.json()['error'] == unknown.json()['error']
