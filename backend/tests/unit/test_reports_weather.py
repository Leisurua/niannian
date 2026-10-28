import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from app.modules.report.metrics import aggregate, classify
from app.modules.report.service import period
from app.modules.weather.service import WeatherService
from app.platform.errors import AppError
from app.platform.identifiers import utcnow


def test_local_classification_and_unrelated_speakers():
    assert classify('我今天很开心。以前上班的时候喜欢种花。')[0] == ['HAPPY']
    assert classify('我想女儿了')[0] == ['MISS_FAMILY']
    for text in ('我不开心', '我没有担心', '你孤单吗', '女儿说我很难过', '“我很开心”', '如果我很孤单', '我想女儿了吗'):
        assert classify(text)[0] == []
    assert classify('年轻时包饺子')[1] == ['DUMPLINGS', 'WORK_STORY']


def test_aggregation_local_midnight_unique_sessions_and_no_empty_topic_cluster():
    zone = ZoneInfo('Asia/Shanghai')
    rows = [SimpleNamespace(conversation_id=cid, occurred_at=datetime.fromisoformat(stamp), duration_seconds=10,
        emotions=emotions, topics=topics, simulated=mock) for cid, stamp, emotions, topics, mock in [
        ('a', '2026-10-18T16:10:00+00:00', ['HAPPY'], ['DUMPLINGS'], False),
        ('a', '2026-10-19T14:10:00+00:00', ['HAPPY'], ['DUMPLINGS'], False),
        ('b', '2026-10-20T01:10:00+00:00', [], ['DUMPLINGS'], True),
        ('c', '2026-10-20T02:10:00+00:00', [], [], False),
        ('d', '2026-10-25T16:00:00+00:00', [], [], False),
    ]]
    result = aggregate(rows, date(2026, 10, 19), date(2026, 10, 26), zone)
    assert (result['sessions'], result['turns'], result['night_turns'], result['active_seconds']) == (3, 4, 2, 40)
    assert result['days'][0]['sessions'] == 1
    assert result['days'][0]['first_interaction'].endswith('00:10:00+08:00')
    assert result['repeated_topics'] == [dict(topic='包饺子', sessions=2)]
    assert result['emotions']['开心'] == 2
    assert result['unclassified_topic_turns'] == 1
    assert result['simulated_turns'] == 1


def test_period_validates_range_and_dst():
    now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    _, since, until = period(date(2026, 11, 1), date(2026, 11, 2), 'America/New_York', now=now)
    assert (until - since).total_seconds() == 25 * 3600
    for start, end, zone in [(date(2026, 11, 2), date(2026, 11, 1), 'UTC'),
            (date(2026, 11, 1), date(2026, 11, 2), 'invalid'), (date(2026, 9, 1), date(2026, 9, 2), 'UTC')]:
        with pytest.raises(AppError):
            period(start, end, zone, now=now)


def transport(payload=None, status=200):
    def reply(request):
        assert 'authorization' not in request.headers
        if request.url.path.endswith('/get'):
            assert request.url.params['id'] == '1816670'
            return httpx.Response(200, json={'id': 1816670, 'name': 'Beijing', 'latitude': 39.9, 'longitude': 116.4})
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'results': []})
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(reply)


def weather_payload(**changes):
    return dict(current_units={'temperature_2m': '°C'}, utc_offset_seconds=28800,
        current=dict(temperature_2m=12, weather_code=3, time=int(utcnow().timestamp())) | changes)


def test_weather_city_lookup_current_attribution_and_empty_search():
    service = WeatherService(transport(weather_payload()))
    result = asyncio.run(service.current(1816670))
    assert result['temperature_c'] == 12 and result['description'] == '阴'
    assert result['source']['name'] == 'Open-Meteo'
    assert result['city']['id'] == 1816670
    assert asyncio.run(service.cities('不存在的城市'))['items'] == []


@pytest.mark.parametrize('payload,status', [
    (weather_payload(time=int((utcnow() - timedelta(hours=4)).timestamp())), 200),
    (weather_payload(time=int((utcnow() + timedelta(hours=1)).timestamp())), 200),
    (weather_payload(temperature_2m=None), 200), (weather_payload(temperature_2m=True), 200),
    ({'current': {}}, 200), ({'error': True}, 200), ({}, 429), ({}, 302),
])
def test_weather_never_returns_invalid_or_stale_data(payload, status):
    with pytest.raises(AppError) as caught:
        asyncio.run(WeatherService(transport(payload, status)).current(1816670))
    assert caught.value.code == 'WEATHER_UNAVAILABLE'


def test_weather_timeout_is_safe():
    def timeout(request):
        raise httpx.ReadTimeout('private upstream error', request=request)
    with pytest.raises(AppError) as caught:
        asyncio.run(WeatherService(httpx.MockTransport(timeout)).cities('北京'))
    assert 'private' not in caught.value.message


def daily_payload():
    return dict(timezone='Asia/Shanghai', daily_units=dict(temperature_2m_min='°C', temperature_2m_max='°C',
        precipitation_probability_max='%'), daily=dict(time=[utcnow().astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()],
        weather_code=[63], temperature_2m_min=[12], temperature_2m_max=[18], precipitation_probability_max=[75]))


def test_weather_today_uses_daily_forecast_not_current_conditions():
    payload = daily_payload()
    def respond(request):
        if request.url.path.endswith('/get'):
            return httpx.Response(200, json=dict(id=1816670, name='Beijing', latitude=39.9, longitude=116.4))
        assert 'precipitation_probability_max' in request.url.params['daily']
        assert 'current' not in request.url.params
        assert request.url.params['timezone'] == 'auto'
        return httpx.Response(200, json=payload)
    result = asyncio.run(WeatherService(httpx.MockTransport(respond)).today(1816670))
    assert result['description'] == '雨' and result['precipitation_probability_max'] == 75
    assert result['source']['name'] == 'Open-Meteo'


@pytest.mark.parametrize('field,value', [('time', ['2000-01-01']), ('weather_code', [100]),
    ('temperature_2m_min', [100]), ('temperature_2m_max', [None]), ('temperature_2m_max', [5]),
    ('precipitation_probability_max', [True]), ('precipitation_probability_max', [101]),
    ('precipitation_probability_max', []), ('precipitation_probability_max', [1, 2])])
def test_daily_forecast_rejects_invalid_or_wrong_day_data(field, value):
    payload = daily_payload()
    payload['daily'][field] = value
    with pytest.raises(AppError, match='今日预报'):
        asyncio.run(WeatherService(transport(payload)).today(1816670))
