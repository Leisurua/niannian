import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from niannian_desktop.api import ApiClient, ApiError


def test_report_reason_and_owner_survive_access_token_refresh():
    client = ApiClient('http://localhost:8000')
    client.access_token, client.refresh_token = 'old', 'refresh'
    calls = []
    def exchange(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if len(calls) == 1:
            raise ApiError(401, 'AUTH_TOKEN_EXPIRED', 'expired')
        if path == '/v1/auth/refresh':
            return {'access_token': 'new', 'refresh_token': 'renewed'}
        return {'text': '交流观察线索'}
    client._exchange = exchange
    assert client.weekly_report('family', 'elder', '2026-10-19', 'FOLLOW_UP')['text'] == '交流观察线索'
    assert calls[0][2]['access_reason'] == calls[2][2]['access_reason'] == 'FOLLOW_UP'
    query = parse_qs(urlsplit(calls[2][1]).query)
    assert query['owner_user_id'] == ['elder'] and query['timezone'] == ['Asia/Shanghai']


def test_report_sends_access_reason_header_and_weather_only_city_id():
    client = ApiClient('http://localhost:8000'); client.access_token = 'test-token'
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return json.dumps({'text': '交流观察线索'}).encode()
    with patch('niannian_desktop.api.urlopen', return_value=Response()) as opened:
        client.weekly_report('family', 'elder', '2026-10-19', 'FAMILY_CHECK_IN')
        assert opened.call_args.args[0].get_header('X-access-reason') == 'FAMILY_CHECK_IN'
        client.weather_current(1816670)
        query = parse_qs(urlsplit(opened.call_args.args[0].full_url).query)
        assert query == {'city_id': ['1816670']}
