import asyncio
import base64
import json

import httpx
import pytest
from app.integrations.family_voice import CosyVoice
from app.platform.config import Settings
from app.platform.errors import AppError


def settings():
    return Settings(app_env='dev', family_voice_enabled=True,
                    family_voice_workspace_id='fictional', family_voice_api_key='fictional-key')


def test_disabled_provider_never_calls_network():
    with pytest.raises(AppError) as error:
        CosyVoice(Settings(family_voice_enabled=False))
    assert error.value.code == 'VOICE_NOT_CONFIGURED'


def test_stream_is_bounded_pcm_and_uses_fixed_provider():
    pcm = b'\0\1' * 10000
    def handle(request):
        body = json.loads(request.content)
        assert request.url.host == 'fictional.cn-beijing.maas.aliyuncs.com'
        assert body['model'] == 'cosyvoice-v3.5-flash'
        assert body['input']['format'] == 'pcm'
        return httpx.Response(200, text='data: ' + json.dumps({'output': {'audio': {
            'data': base64.b64encode(pcm).decode()}}}) + '\n\ndata: [DONE]\n')
    async def run():
        provider = CosyVoice(settings(), transport=httpx.MockTransport(handle))
        parts = [part async for part in provider.stream('虚构测试文本', 'voice-test')]
        assert b''.join(parts) == pcm
        assert max(map(len, parts)) <= 8192
    asyncio.run(run())


@pytest.mark.parametrize('body', ['data: {"code":"secret-provider-detail"}\n',
                                'data: {"output":{"audio":{"data":"!!"}}}\n', ''])
def test_invalid_stream_is_safe_failure(body):
    async def run():
        provider = CosyVoice(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body)))
        with pytest.raises(AppError) as error:
            _ = [part async for part in provider.stream('虚构测试文本', 'voice-test')]
        assert error.value.code == 'VOICE_PROVIDER_UNAVAILABLE'
        assert 'secret-provider-detail' not in str(error.value)
    asyncio.run(run())


def test_clone_sends_inline_audio_and_binds_model():
    def handle(request):
        body = json.loads(request.content)
        assert body['input']['audio'] == 'data:audio/wav;base64,' + base64.b64encode(b'fictional').decode()
        assert body['input']['target_model'] == CosyVoice.model
        return httpx.Response(200, json={'output': {'voice_id': CosyVoice.model + '-test-123'}})
    provider = CosyVoice(settings(), transport=httpx.MockTransport(handle))
    assert asyncio.run(provider.create(b'fictional', 'test')).endswith('-test-123')
