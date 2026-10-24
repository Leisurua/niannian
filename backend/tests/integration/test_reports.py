import asyncio
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
from app.main import app
from app.modules.conversation.models import Conversation
from app.modules.report import metrics
from app.modules.weather.service import WeatherService
from app.platform.identifiers import utcnow
from sqlalchemy import text

from backend.tests.support import URL, grant, household, login, post, reminder_body
from backend.tests.integration.test_summary_proactive import converse

pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable TEST_DATABASE_URL required')


def enable(client, home):
    response = post(client, '/v1/consents', home[4], dict(family_id=home[0], subject_user_id=home[3],
        grantee_user_id=home[3], scope='INTERACTION_STATS', source='SETTINGS'))
    assert response.status_code == 201, response.text
    return response.json()['id']


def report(client, home, headers=None, **params):
    return client.get('/v1/reports/weekly', params=dict(family_id=home[0], owner_user_id=home[3], **params),
        headers={**(headers or home[2]), 'X-Access-Reason': 'FAMILY_CHECK_IN'})


def test_live_turns_template_statistics_and_delete(system):
    client, engine, factory, _ = system
    home = household(client)
    grant(client, home, 'INTERACTION_STATS')
    converse(client, home, '我今天很开心，年轻时包饺子')
    assert report(client, home).json()['current']['interaction']['turns'] == 0
    enable(client, home)
    ids = [converse(client, home, '我今天很开心，年轻时包饺子'), converse(client, home, '我很高兴，喜欢做饺子')]
    response = report(client, home)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    data = response.json()
    assert data['current']['interaction']['turns'] == 2
    assert data['current']['interaction']['sessions'] == 2
    assert data['current']['interaction']['emotions']['开心'] == 2
    assert data['current']['interaction']['repeated_topics'] == [{'topic': '包饺子', 'sessions': 2}]
    assert data['comparison']['sessions_delta'] is None
    assert '交流观察线索' in data['text'] and 'Mock' in data['text']
    assert data['current']['attention'] is None
    assert report(client, home).json()['current']['interaction'] == data['current']['interaction']
    # Duplicate sequence is a no-op; no input or reply is persisted in metrics.
    async def duplicate():
        async with factory() as db:
            row = await db.get(Conversation, UUID(ids[0]))
            await metrics.collect(db, row, 2, 'synthetic-secret', utcnow() - timedelta(seconds=1), utcnow())
            await db.commit()
    asyncio.run(duplicate())
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT * FROM interaction_metric')).all()
        assert len(rows) == 2 and 'synthetic-secret' not in str(rows)
    period = data['current']['period']
    stats = client.get('/v1/statistics', headers=home[4], params=dict(family_id=home[0], owner_user_id=home[3],
        start=period['start'], end=period['end_exclusive'])).json()
    assert stats['interaction'] == data['current']['interaction']
    # A family member can only delete their own collection, not the elder's.
    assert client.delete('/v1/reports/data', params={'family_id': home[0]}, headers=home[2]).status_code == 204
    assert report(client, home).json()['current']['interaction']['turns'] == 2
    assert client.delete('/v1/reports/data', params={'family_id': home[0]}, headers=home[4]).status_code == 204
    assert report(client, home).json()['current']['interaction']['turns'] == 0
    async def late_result():
        async with factory() as db:
            row = await db.get(Conversation, UUID(ids[0]))
            await metrics.collect(db, row, 99, '我很开心', row.started_at, utcnow())
            await db.commit()
    asyncio.run(late_result())
    assert report(client, home).json()['current']['interaction']['turns'] == 0


def test_permissions_revocation_and_expiry_do_not_resurrect(system):
    client, engine, _, _ = system
    home = household(client)
    own = enable(client, home)
    cid = converse(client, home)
    assert report(client, home).status_code == 403
    share = grant(client, home, 'INTERACTION_STATS')
    assert report(client, home).json()['current']['interaction']['turns'] == 1
    assert client.get('/v1/reports/weekly', headers=home[2], params=dict(family_id=home[0], owner_user_id=home[3])).status_code == 422
    _, outsider = login(client, 'demo-caregiver')
    assert report(client, home, outsider).status_code in (403, 404)
    post(client, '/v1/consents/' + share + '/revoke', home[4])
    assert report(client, home).status_code == 403
    grant(client, home, 'INTERACTION_STATS')
    post(client, '/v1/consents/' + own + '/revoke', home[4])
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM interaction_metric')).scalar() == 0
    enable(client, home)
    assert report(client, home).json()['current']['interaction']['turns'] == 0
    cid = converse(client, home)
    with engine.begin() as conn:
        conn.execute(text('UPDATE conversation SET deleted_at=now() WHERE id=:id'), {'id': cid})
    assert report(client, home).json()['current']['interaction']['turns'] == 0
    converse(client, home)
    with engine.begin() as conn:
        conn.execute(text("UPDATE consent SET expires_at=now()-interval '1 second' WHERE scope='INTERACTION_STATS' AND subject_user_id=grantee_user_id AND status='GRANTED'"))
    assert report(client, home).json()['current']['interaction']['turns'] == 0


def test_week_comparison_range_and_medication_scope(system):
    client, engine, _, _ = system
    home = household(client); enable(client, home); grant(client, home, 'INTERACTION_STATS')
    ids = [converse(client, home), converse(client, home)]
    monday = utcnow().astimezone(ZoneInfo('Asia/Shanghai')).date()
    monday -= timedelta(days=monday.weekday())
    with engine.begin() as conn:
        conn.execute(text('UPDATE interaction_metric SET occurred_at=:at WHERE conversation_id=:id'),
            dict(at=str(monday - timedelta(days=3)) + ' 10:00:00+08', id=ids[0]))
    data = report(client, home).json()
    assert data['comparison']['sessions_delta'] == 0
    assert any('用药提醒未计入' in line for line in data['current']['missing_data'])
    assert report(client, home, week_start=str(monday + timedelta(days=1))).status_code == 422
    assert report(client, home, timezone='invalid').status_code == 422
    assert report(client, home, week_start=str(monday - timedelta(days=70))).status_code == 422
    assert report(client, home, week_start='9999-12-27').status_code == 422
    # Expired data excluded immediately, then physically removed by worker.
    with engine.begin() as conn:
        conn.execute(text("UPDATE interaction_metric SET occurred_at=now()-interval '36 days', retention_until=now()-interval '1 day'"))
    assert report(client, home).json()['current']['interaction']['turns'] == 0
    async def cleanup():
        async with system[2]() as db:
            await metrics.maintenance(db)
            await db.commit()
    asyncio.run(cleanup())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM interaction_metric')).scalar() == 0


def test_weather_api_auth_validations_and_no_coordinate_input(system):
    client, _, _, _ = system
    _, headers = login(client, 'demo-elder')
    assert client.get('/v1/weather/cities?q=Beijing').status_code == 401
    def reply(request):
        assert 'authorization' not in request.headers
        return httpx.Response(200, json={'results': []})
    app.state.weather_service = WeatherService(httpx.MockTransport(reply))
    try:
        response = client.get('/v1/weather/cities?q=Beijing', headers=headers)
        assert response.status_code == 200 and response.json()['items'] == []
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/v1/weather/current?latitude=1&longitude=2', headers=headers).status_code == 422
        assert client.get('/v1/weather/current?city_id=-1', headers=headers).status_code == 422
    finally:
        del app.state.weather_service


def test_reminder_counts_use_execution_feedback_and_current_health_grant(system):
    from app.modules.reminder.models import ReminderExecution
    from app.platform.identifiers import uuid7
    client, _, factory, _ = system
    home = household(client); grant(client, home, 'INTERACTION_STATS')
    health = grant(client, home, 'HEALTH_MEDICATION')
    water = post(client, '/v1/reminders', home[2], reminder_body(home)).json()['id']
    medication = post(client, '/v1/reminders', home[2], reminder_body(home, type='MEDICATION')).json()['id']
    async def seed():
        async with factory() as db:
            due = utcnow() - timedelta(minutes=2)
            for rid, feedback in [(water, 'DONE'), (medication, 'NO_RESPONSE')]:
                db.add(ReminderExecution(id=uuid7(), reminder_id=UUID(rid), owner_user_id=UUID(home[3]),
                    occurrence_key='report-fixture', scheduled_at=due, local_date=due.date(), local_time=due.time().replace(tzinfo=None),
                    triggered_at=due, feedback_status=feedback, feedback_at=due + timedelta(seconds=45) if feedback == 'DONE' else None,
                    source='ONLINE', attempt_count=1))
            await db.commit()
    asyncio.run(seed())
    data = report(client, home).json()['current']['reminders']
    assert data['total'] == 2 and data['feedback']['DONE'] == 1 and data['feedback']['NO_RESPONSE'] == 1
    assert data['average_response_seconds'] == 45
    post(client, '/v1/consents/' + health + '/revoke', home[4])
    data = report(client, home).json()['current']['reminders']
    assert data['total'] == 1 and data['feedback']['NO_RESPONSE'] == 0
