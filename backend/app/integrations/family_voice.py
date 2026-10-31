"""Beijing CosyVoice adapter. Audio and provider errors never enter logs."""
import asyncio
import base64
import json
import re

import httpx

from app.platform.errors import AppError


class CosyVoice:
    model = 'cosyvoice-v3.5-flash'

    def __init__(self, settings, *, transport=None):
        if not settings.family_voice_enabled or not settings.family_voice_api_key or not settings.family_voice_workspace_id:
            raise AppError('VOICE_NOT_CONFIGURED', '家人音色服务尚未配置。', 503)
        if settings.app_env != 'dev':
            raise AppError('VOICE_NOT_CONFIGURED', '真实声音服务仅在开发联调环境启用。', 503)
        self.base = f'https://{settings.family_voice_workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts'
        self.headers = {'Authorization': 'Bearer ' + settings.family_voice_api_key.get_secret_value()}
        self.transport = transport

    async def _manage(self, action, **values):
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport, follow_redirects=False) as client:
                async with client.stream('POST', self.base + '/customization', headers=self.headers,
                        json={'model': 'voice-enrollment', 'input': {'action': action, **values}}) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for part in response.aiter_bytes():
                        data.extend(part)
                        if len(data) > 65536:
                            raise ValueError('size')
                result = json.loads(data)
                if result.get('code'):
                    raise ValueError('provider error')
                return result.get('output', {})
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise AppError('VOICE_PROVIDER_UNAVAILABLE', '声音服务暂不可用，请稍后重试。', 503) from None

    async def create(self, sample: bytes, prefix: str) -> str:
        if not re.fullmatch(r'[a-zA-Z0-9]{1,10}', prefix):
            raise ValueError('Invalid voice prefix')
        result = await self._manage('create_voice', target_model=self.model, prefix=prefix,
            audio='data:audio/wav;base64,' + base64.b64encode(sample).decode('ascii'), language_hints=['zh'])
        voice = result.get('voice_id')
        if not isinstance(voice, str) or not voice.startswith(self.model + '-') or len(voice) > 256:
            raise AppError('VOICE_PROVIDER_UNAVAILABLE', '声音制作结果无法确认。', 503)
        return voice

    async def query(self, voice_id):
        return (await self._manage('query_voice', voice_id=voice_id)).get('status', 'UNKNOWN')

    async def delete(self, voice_id):
        await self._manage('delete_voice', voice_id=voice_id)

    async def stream(self, text, voice_id, speed=1.0):
        if not text or len(text) > 2000 or not 0.5 <= speed <= 2:
            raise ValueError('Invalid speech input')
        payload = {'model': self.model, 'input': {'text': text, 'voice': voice_id,
            'format': 'pcm', 'sample_rate': 24000, 'rate': speed}}
        try:
            async with asyncio.timeout(360):
                async with httpx.AsyncClient(timeout=15, transport=self.transport, follow_redirects=False) as client:
                    async with client.stream('POST', self.base + '/SpeechSynthesizer',
                            headers={**self.headers, 'X-DashScope-SSE': 'enable'}, json=payload) as response:
                        response.raise_for_status()
                        buffer = bytearray()
                        total = 0
                        completed = False
                        async for block in response.aiter_bytes():
                            buffer.extend(block)
                            if len(buffer) > 2_000_000:
                                raise ValueError('Oversized SSE event')
                            while b'\n' in buffer:
                                line, _, rest = buffer.partition(b'\n')
                                buffer = bytearray(rest)
                                if not line.startswith(b'data:'):
                                    continue
                                value = line[5:].strip()
                                if value == b'[DONE]':
                                    completed = True
                                    continue
                                if not value:
                                    continue
                                event = json.loads(value)
                                if event.get('code'):
                                    raise ValueError('Provider error')
                                completed = completed or event.get('output', {}).get('finish_reason') == 'stop'
                                encoded = event.get('output', {}).get('audio', {}).get('data')
                                if encoded:
                                    pcm = base64.b64decode(encoded, validate=True)
                                    total += len(pcm)
                                    if total > 24_000 * 2 * 300 or len(pcm) % 2:
                                        raise ValueError('Invalid PCM')
                                    for start in range(0, len(pcm), 8192):
                                        yield pcm[start:start + 8192]
                        if not total or not completed:
                            raise ValueError('Empty audio')
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
            raise AppError('VOICE_PROVIDER_UNAVAILABLE', '家人声音暂不可用，已改用普通声音。', 503) from None
