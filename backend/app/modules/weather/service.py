"""Weather for a manually selected public city ID. Never accepts device coordinates."""
import json
import math
from datetime import datetime, timedelta, timezone

import httpx

from app.platform.errors import AppError
from app.platform.identifiers import utcnow

SOURCE = {'name': 'Open-Meteo', 'url': 'https://open-meteo.com/'}


def description(code):
    for codes, label in [((0,), '晴'), ((1,), '大部晴朗'), ((2,), '多云'), ((3,), '阴'),
        ((45, 48), '雾'), ((51, 53, 55), '毛毛雨'), ((56, 57, 66, 67), '冻雨'), ((61, 63, 65), '雨'),
        ((71, 73, 75, 77), '雪'), ((80, 81, 82), '阵雨'), ((85, 86), '阵雪'), ((95, 96, 99), '雷暴')]:
        if code in codes:
            return label
    return '天气状态未知'


def number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('Invalid weather field')
    return value


def city_view(row):
    if not isinstance(row['name'], str) or not row['name'].strip():
        raise ValueError('Invalid city name')
    city_id = row['id']
    if type(city_id) is not int or city_id <= 0:
        raise ValueError('Invalid public city ID')
    return dict(id=city_id, label=' · '.join(dict.fromkeys(str(row[key]) for key in ('name', 'admin1', 'country') if row.get(key))))


class WeatherService:
    def __init__(self, transport=None):
        self.transport = transport

    async def fetch(self, url, params):
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, transport=self.transport) as client:
                async with client.stream('GET', url, params=params) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > 131072:
                            raise ValueError('Oversized weather response')
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get('error'):
                raise ValueError('Invalid weather response')
            return result
        except (httpx.HTTPError, ValueError):
            raise AppError('WEATHER_UNAVAILABLE', '天气服务暂不可用，请稍后重试。', 503) from None

    async def cities(self, query):
        query = query.strip()
        if len(query) < 2:
            raise AppError('VALIDATION_ERROR', '请输入至少两个字符的城市名。', 422)
        body = await self.fetch('https://geocoding-api.open-meteo.com/v1/search',
            dict(name=query, count=10, language='zh', format='json'))
        try:
            rows = body.get('results', [])
            if not isinstance(rows, list):
                raise ValueError('Invalid city list')
            return dict(items=[city_view(row) for row in rows[:10]], source=SOURCE)
        except (KeyError, ValueError, TypeError):
            raise AppError('WEATHER_UNAVAILABLE', '城市搜索数据不可用，请稍后重试。', 503) from None

    async def current(self, city_id):
        # Coordinates come solely from the provider's public city catalogue.
        city = await self.fetch('https://geocoding-api.open-meteo.com/v1/get', dict(id=city_id))
        try:
            selected = city_view(city)
            if selected['id'] != city_id:
                raise ValueError('City mismatch')
            latitude = number(city['latitude'], -90, 90)
            longitude = number(city['longitude'], -180, 180)
        except (KeyError, ValueError, TypeError):
            raise AppError('WEATHER_UNAVAILABLE', '城市信息不可用，请重新选择城市。', 503) from None
        body = await self.fetch('https://api.open-meteo.com/v1/forecast', dict(latitude=latitude, longitude=longitude,
            current='temperature_2m,weather_code', temperature_unit='celsius', timezone='auto', timeformat='unixtime', forecast_days=1))
        try:
            current = body['current']
            if body['current_units']['temperature_2m'] != '°C':
                raise ValueError('Unexpected temperature units')
            temperature = number(current['temperature_2m'], -100, 70)
            code = number(current['weather_code'], 0, 1000)
            stamp = datetime.fromtimestamp(number(current['time'], 0, 4102444800), timezone.utc)
            now = utcnow()
            if stamp < now - timedelta(hours=3) or stamp > now + timedelta(minutes=15):
                raise ValueError('Stale weather')
            offset = number(body['utc_offset_seconds'], -43200, 50400)
            return dict(city=selected, temperature_c=temperature, weather_code=code, description=description(code),
                observed_at=stamp.isoformat(), utc_offset_seconds=offset, fetched_at=now.isoformat(), source=SOURCE)
        except (KeyError, ValueError, TypeError, OverflowError):
            raise AppError('WEATHER_UNAVAILABLE', '天气数据无效或已过期，请刷新重试。', 503) from None
