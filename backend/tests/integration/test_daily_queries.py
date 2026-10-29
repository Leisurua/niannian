import asyncio
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo
from starlette.websockets import WebSocketDisconnect

import httpx
import pytest
from sqlalchemy import text

from app.main import app
from app.modules.conversation import daily
from app.modules.conversation import api as conversation_api
from app.modules.reminder.service import tick
from app.modules.weather.service import WeatherService
from app.platform.config import get_settings
from app.platform.identifiers import utcnow
from backend.tests.support import URL, household, post, reminder_body, start, handshake, ws_frame

pytestmark = pytest.mark.skipif(not URL, reason='Set TEST_DATABASE_URL to run PostgreSQL integration tests')


def ask(ws, cid, sequence, value, **context):
    ws.send_json(ws_frame(cid, 'text.input', sequence, dict(text=value, **context)))
    assert ws.receive_json()['payload']['state'] == 'THINKING'
    response = ws.receive_json()
    assert response['type'] == 'assistant.text', response
    assert response['in_reply_to'] == sequence
    assert ws.receive_json()['payload']['state'] == 'IDLE'
    return response['payload']


def test_voice_reminder_done_later_and_worker_use_same_persistent_execution(system):
    client, engine, factory, _ = system
    home = household(client)
    now = utcnow()
    assert post(client, '/v1/consents', home[4], dict(family_id=home[0], subject_user_id=home[3],
        grantee_user_id=home[3], scope='INTERACTION_STATS', source='SETTINGS')).status_code == 201
    for title, minute in [('喝水提醒', 1), ('散步提醒', 2)]:
        due = now + timedelta(minutes=minute)
        result = post(client, '/v1/reminders', home[2], reminder_body(home, title=title,
            schedule_time_local=due.strftime('%H:%M:%S'), start_date=now.date().isoformat()))
        assert result.status_code == 201
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        schedule = ask(ws, cid, 2, '今天有什么安排', timezone='UTC')
        assert schedule['source_labels'] == ['本人提醒记录']
        assert '喝水提醒' in schedule['text'] and '散步提醒' in schedule['text']
        ambiguous = ask(ws, cid, 3, '完成了', timezone='UTC')
        assert '还没有更改' in ambiguous['text']
        done = ask(ws, cid, 4, '第一项完成了', timezone='UTC')
        assert done['reminders_changed'] is True and '记录为完成' in done['text']
        again = ask(ws, cid, 5, '第一项完成了', timezone='UTC')
        assert '没有重复更改' in again['text'] and not again.get('reminders_changed')
        later = ask(ws, cid, 6, '第二项二十分钟后再提醒我', timezone='UTC')
        assert later['reminders_changed'] is True and '再提醒' in later['text']
        ws.send_json(ws_frame(cid, 'repeat', 7))
        assert ws.receive_json()['payload']['text'] == later['text']
        assert ws.receive_json()['payload']['state'] == 'IDLE'
    with engine.connect() as connection:
        rows = connection.execute(text('SELECT feedback_status,next_due_at FROM reminder_execution ORDER BY scheduled_at')).all()
        assert len(rows) == 2 and [r[0] for r in rows] == ['DONE', 'LATER']
        later_time = rows[1][1]
        assert 1190 < (later_time - now).total_seconds() < 1230
        assert connection.execute(text("SELECT count(*) FROM audit_log WHERE action='REMINDER_FEEDBACK'")).scalar() == 2
        assert connection.execute(text('SELECT count(*) FROM interaction_metric')).scalar() == 5
        assert connection.execute(text('SELECT count(*) FROM interaction_metric WHERE simulated')).scalar() == 0
    async def run():
        async with factory() as db:
            await tick(db, get_settings(), later_time + timedelta(seconds=1))
            await db.commit()
    asyncio.run(run())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM reminder_execution WHERE feedback_status='PENDING'")).scalar() == 1
        assert connection.execute(text('SELECT count(*) FROM reminder_execution')).scalar() == 2


def test_dates_and_forecast_bypass_unavailable_llm_and_missing_city_is_explicit(system, monkeypatch):
    client, engine, _, _ = system
    home = household(client)
    def respond(request):
        assert 'authorization' not in request.headers
        if request.url.path.endswith('/get'):
            return httpx.Response(200, json=dict(id=1816670, name='虚构天气测试城市', latitude=39.9, longitude=116.4))
        assert 'daily' in request.url.params and 'current' not in request.url.params
        return httpx.Response(200, json=dict(timezone='Asia/Shanghai',
            daily_units=dict(temperature_2m_min='°C', temperature_2m_max='°C', precipitation_probability_max='%'),
            daily=dict(time=[utcnow().astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()],
                weather_code=[63], temperature_2m_min=[10], temperature_2m_max=[18], precipitation_probability_max=[80])))
    monkeypatch.setattr(app.state, 'weather_service', WeatherService(httpx.MockTransport(respond)), raising=False)
    rag_calls = []
    async def no_rag(*args, **kwargs):
        rag_calls.append(True)
        raise AssertionError('Daily queries must bypass RAG and external LLM processing')
    monkeypatch.setattr('app.modules.conversation.api.rag.retrieve', no_rag)
    class UnavailableOrchestrator:
        llm = SimpleNamespace(provider='openai_compatible')

        async def handle(self, **kwargs):
            raise AssertionError('Daily queries must work with an unavailable LLM')
    monkeypatch.setattr(conversation_api, 'configured_orchestrator', lambda settings: UnavailableOrchestrator())
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        date = ask(ws, cid, 2, '今天几号', timezone='Asia/Shanghai')
        assert f'{utcnow().astimezone(ZoneInfo("Asia/Shanghai")).day}日' in date['text']
        assert date['source_labels'] == ['服务端时间']
        missing = ask(ws, cid, 3, '今天会下雨吗')
        assert '选择城市' in missing['text']
        weather = ask(ws, cid, 4, '今天会下雨吗', weather_city_id=1816670)
        assert '80%' in weather['text'] and '10到18摄氏度' in weather['text']
        assert weather['source_labels'] == ['Open-Meteo 今日预报']
        assert '预报' in weather['text']
    assert rag_calls == []
    with engine.connect() as connection:
        assert '虚构天气测试城市' not in str(connection.execute(text('SELECT provider_metadata,summary_text FROM conversation')).all())


def test_feedback_rechecks_changed_schedule_negation_and_family_isolation(system):
    client, engine, _, _ = system
    home = household(client)
    other = household(client, 'demo-other')
    original = post(client, '/v1/reminders', home[2], reminder_body(home, title='本家庭喝水')).json()
    assert post(client, '/v1/reminders', other[2], reminder_body(other, title='另一个家庭的私有安排')).status_code == 201
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        result = ask(ws, cid, 2, '今天有什么安排', timezone='UTC')
        assert '本家庭喝水' in result['text'] and '私有安排' not in result['text']
        for sequence, value in enumerate(('我没有完成', '第一项完成了吗', '如果第一项完成了'), 3):
            assert '尚未更改' in ask(ws, cid, sequence, value, timezone='UTC')['text']
        ask(ws, cid, 6, '今天有什么安排', timezone='UTC')
        changed = client.patch('/v1/reminders/' + original['id'], headers={**home[2], 'If-Match': '1'},
            json=reminder_body(home, title='修改后的安排'))
        assert changed.status_code == 200
        stale = ask(ws, cid, 7, '第一项完成了', timezone='UTC')
        assert '已变更' in stale['text'] and not stale.get('reminders_changed')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM reminder_execution')).scalar() == 0
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        ws.receive_json()
        assert '还没有更改' in ask(ws, cid, 8, '完成了', timezone='UTC')['text']


def test_interrupt_discards_prepared_feedback_before_any_write(system, monkeypatch):
    client, engine, _, _ = system
    home = household(client)
    post(client, '/v1/reminders', home[2], reminder_body(home))
    entered = threading.Event()
    original_answer = daily.prepare_answer
    async def held(*args, **kwargs):
        result = await original_answer(*args, **kwargs)
        if result and result.kind == 'FEEDBACK':
            entered.set()
            await asyncio.Event().wait()
        return result
    monkeypatch.setattr(daily, 'prepare_answer', held)
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        ask(ws, cid, 2, '今天有什么安排', timezone='UTC')
        ws.send_json(ws_frame(cid, 'text.input', 3, {'text': '第一项完成了', 'timezone': 'UTC'}))
        assert ws.receive_json()['payload']['state'] == 'THINKING'
        assert entered.wait(3)
        ws.send_json(ws_frame(cid, 'interrupt', 4))
        assert ws.receive_json()['payload']['state'] == 'LISTENING'
        assert '待处理' in ask(ws, cid, 5, '今天有什么安排', timezone='UTC')['text']
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM reminder_execution')).scalar() == 0


def test_family_revocation_does_not_wait_for_weather_and_prevents_publication(system, monkeypatch):
    client, _, _, _ = system
    home = household(client)
    entered = threading.Event()
    class HeldWeather:
        async def today(self, city_id):
            entered.set()
            await asyncio.Event().wait()
    monkeypatch.setattr(app.state, 'weather_service', HeldWeather(), raising=False)
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': '今天会下雨吗', 'weather_city_id': 1816670}))
        assert ws.receive_json()['payload']['state'] == 'THINKING'
        assert entered.wait(3)
        members = client.get('/v1/families/' + home[0] + '/members', headers=home[2]).json()['items']
        elder = next(member for member in members if member['user_id'] == home[3])
        result = client.patch('/v1/families/' + home[0] + '/members/' + elder['id'],
            headers={**home[2], 'If-Match': str(elder['version'])}, json={'status': 'REVOKED'})
        assert result.status_code == 200
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_today_projection_uses_schedule_rules_and_requested_local_day(system):
    client, _, factory, _ = system
    home = household(client)
    for title, clock, day in [('上海早上', '23:30:00', '2026-10-27'), ('上海凌晨', '16:30:00', '2026-10-27'),
            ('上海前一天', '15:30:00', '2026-10-27'), ('上海次日', '16:30:00', '2026-10-28')]:
        assert post(client, '/v1/reminders', home[2], reminder_body(home, title=title, timezone='UTC',
            schedule_time_local=clock, start_date=day, recurrence_kind='ONCE')).status_code == 201
    async def run():
        async with factory() as db:
            return await daily.today_choices(db, SimpleNamespace(user_id=UUID(home[3])),
                SimpleNamespace(family_id=UUID(home[0])), ZoneInfo('Asia/Shanghai'), datetime(2026, 10, 28, 0, 5, tzinfo=timezone.utc))
    choices = asyncio.run(run())
    assert {c.title for c in choices} == {'上海早上', '上海凌晨'}


def test_snoozed_older_occurrence_is_included_on_its_new_day(system):
    client, _, factory, _ = system
    home = household(client)
    now = utcnow()
    scheduled = (now - timedelta(hours=1)).replace(microsecond=0)
    next_day = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    parent = post(client, '/v1/reminders', home[2], reminder_body(home, title='跨日稍后提醒',
        schedule_time_local=scheduled.strftime('%H:%M:%S'), start_date=scheduled.date().isoformat(), recurrence_kind='ONCE')).json()
    result = post(client, '/v1/reminders/' + parent['id'] + '/offline-feedback', home[4],
        dict(reminder_version=1, scheduled_at=scheduled.isoformat(), feedback_at=now.isoformat(),
            status='LATER', next_due_at=next_day.isoformat()))
    assert result.status_code == 200, result.text
    async def run():
        async with factory() as db:
            return await daily.today_choices(db, SimpleNamespace(user_id=UUID(home[3])),
                SimpleNamespace(family_id=UUID(home[0])), ZoneInfo('UTC'), next_day)
    choices = asyncio.run(run())
    assert len(choices) == 1 and choices[0].title == '跨日稍后提醒'
    assert choices[0].status == 'LATER' and choices[0].next_due_at == next_day
    async def trigger():
        async with factory() as db:
            await tick(db, get_settings(), next_day + timedelta(seconds=1))
            await db.commit()
    asyncio.run(trigger())
    triggered = asyncio.run(run())
    assert len(triggered) == 1 and triggered[0].status == 'PENDING'
    assert triggered[0].next_due_at is None and triggered[0].triggered_at == next_day + timedelta(seconds=1)
