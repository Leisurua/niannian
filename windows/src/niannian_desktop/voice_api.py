from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from .api import ApiError, ClientError, _json_or_empty


class VoiceApi:
    def __init__(self, client):
        self.client = client

    def request(self, method, path, body=None):
        return self.client._request(method, path, body=body,
            idempotency_key=str(uuid4()) if method != 'GET' else None)

    def profiles(self, family, available=False):
        return self.request('GET', '/v1/voice-profiles?' + urlencode(dict(family_id=family, available=str(available).lower())))

    def preference(self, family, voice=None, allowed=None):
        if allowed is None:
            return self.request('GET', '/v1/voice-preferences?' + urlencode(dict(family_id=family)))
        return self.request('PUT', '/v1/voice-preferences', dict(family_id=family,
            voice_profile_id=voice, cloud_tts_allowed=allowed))

    def members(self, family):
        rows, cursor = [], None
        while True:
            query = dict(limit=100)
            if cursor:
                query['cursor'] = cursor
            result = self.request('GET', f'/v1/families/{family}/members?' + urlencode(query))
            rows.extend(row for row in result.get('items', []) if row.get('status') == 'ACTIVE')
            if not result.get('page', {}).get('has_more'):
                return rows
            next_cursor = result['page'].get('next_cursor')
            if not next_cursor or next_cursor == cursor:
                raise ClientError('成员列表分页无效。')
            cursor = next_cursor

    def audio(self, profile, kind, data=None):
        method = 'PUT' if data is not None else 'GET'
        client = self.client
        with client._request_lock:
            for attempt in range(2):
                if not client.access_token:
                    raise ClientError('请先登录。')
                headers = {'Authorization': 'Bearer ' + client.access_token, 'Content-Type': 'audio/wav',
                    'Accept': 'application/json' if data is not None else 'audio/wav'}
                try:
                    request = Request(client.base_url + f'/v1/voice-profiles/{profile}/{kind}',
                        data=data, headers=headers, method=method)
                    with urlopen(request, timeout=20) as response:
                        raw = response.read(10 * 1024 * 1024 + 1)
                        if len(raw) > 10 * 1024 * 1024:
                            raise ClientError('音频超过大小限制。')
                        return _json_or_empty(raw) if data is not None else raw
                except HTTPError as exc:
                    value = _json_or_empty(exc.read()).get('error', {})
                    if attempt == 0 and exc.code == 401 and value.get('code') == 'AUTH_TOKEN_EXPIRED' and client.refresh_token:
                        pair = client._exchange('POST', '/v1/auth/refresh', auth=False,
                            body={'refresh_token': client.refresh_token})
                        client.access_token, client.refresh_token = pair['access_token'], pair['refresh_token']
                        continue
                    raise ApiError(exc.code, value.get('code', 'AUDIO_FAILED'), value.get('message', '音频请求失败。')) from None
                except (URLError, OSError):
                    raise ClientError('音频传输失败，请检查网络后重试。') from None
