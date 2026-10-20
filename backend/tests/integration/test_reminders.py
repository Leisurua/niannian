import asyncio
from datetime import timedelta

import pytest
from app.modules.reminder.service import tick
from app.platform.config import get_settings
from app.platform.identifiers import utcnow
from sqlalchemy import text

from backend.tests.support import (
    URL,
    grant,
    household,
    post,
    reminder_body,
)

pytestmark = pytest.mark.skipif(not URL, reason='Set TEST_DATABASE_URL to run PostgreSQL integration tests')

def test_reminder_occurrence_feedback_later_and_no_response(system):
    client, engine, factory, _ = system
    home = household(client)
    created = post(client, '/v1/reminders', home[2], reminder_body(home)).json()
    assert 'id' in created, created
    from datetime import datetime
    due = datetime.fromisoformat(created['next_due_at'])
    async def run(now):
        async with factory() as db:
            await tick(db, get_settings(), now)
            await db.commit()
    asyncio.run(run(due)); asyncio.run(run(due))
    executions = client.get(f"/v1/reminders/{created['id']}/executions", headers=home[2]).json()['items']
    assert len(executions) == 1 and executions[0]['feedback_status'] == 'PENDING'
    eid = executions[0]['id']
    assert post(client, '/v1/reminder-executions/'+eid+'/feedback', home[2], {'status':'DONE'}).status_code == 404
    assert post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'NO_RESPONSE'}).status_code == 422
    later = utcnow() + timedelta(minutes=10)
    result = post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'LATER','next_due_at':later.isoformat()}, key='later-once')
    assert result.status_code == 200
    asyncio.run(run(later + timedelta(seconds=1)))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM reminder_execution')).scalar() == 1
    asyncio.run(run(later + timedelta(hours=2)))
    assert client.get(f"/v1/reminders/{created['id']}/executions", headers=home[2]).json()['items'][0]['feedback_status'] == 'NO_RESPONSE'
    done = post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'DONE'}, key='done-once')
    assert done.status_code == 200
    assert post(client, '/v1/reminder-executions/'+eid+'/feedback', home[4], {'status':'DONE'}, key='done-once').json() == done.json()


def test_reminder_medication_consent_family_selection_and_version(system):
    client, _, _, _ = system
    home = household(client)
    body = reminder_body(home, type='MEDICATION')
    assert post(client, '/v1/reminders', home[2], body).status_code == 403
    assert post(client, '/v1/reminders', home[4], body).status_code == 403
    cid = grant(client, home, 'HEALTH_MEDICATION')
    item = post(client, '/v1/reminders', home[2], body).json()
    changed = client.patch('/v1/reminders/'+item['id'], headers={**home[2],'If-Match':'1'}, json=body|{'title':'新提醒'})
    assert changed.status_code == 200
    assert client.patch('/v1/reminders/'+item['id'], headers={**home[2],'If-Match':'1'}, json=body).status_code == 409
    post(client, '/v1/consents/'+cid+'/revoke', home[4])
    assert client.get('/v1/reminders/'+item['id'], headers=home[2]).status_code == 404
    household(client, 'demo-other')
    no_family = reminder_body(home); no_family.pop('family_id')
    assert post(client, '/v1/reminders', home[4], no_family).status_code == 422


def test_concurrent_same_key_creation_and_worker_tick_are_unique(system):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    client, engine, factory, _ = system
    home = household(client); grant(client, home)
    body = dict(family_id=home[0], subject_user_id=home[3], type='EVENT', title='并发虚构候选',
                content='虚构', required_consent_scope='FAMILY_MEMORY')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(client, '/v1/memories', home[2], body, key='parallel-create'), range(2)))
    assert all(r.status_code == 201 for r in responses)
    assert responses[0].json()['id'] == responses[1].json()['id']
    item = post(client, '/v1/reminders', home[2], reminder_body(home)).json()
    due = datetime.fromisoformat(item['next_due_at'])
    async def run():
        async with factory() as db:
            await tick(db, get_settings(), due)
            await db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: asyncio.run(run()), range(2)))
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM reminder_execution')).scalar() == 1
