import asyncio
import base64
from io import BytesIO
import json
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from app.integrations.avatar_preprocess import place_face
from app.modules.avatar.pipeline import ImageEditor, PipelineError, normalize_illustration


def settings(provider):
    return SimpleNamespace(avatar_generation_enabled=True, app_env='dev', avatar_image_timeout=30,
        avatar_image_provider=provider, avatar_image_base_url='https://image.example.invalid/api',
        avatar_image_api_key='fictional-secret', avatar_image_model='fictional-editor')


def picture(mode='RGB'):
    out = BytesIO(); Image.new(mode, (512, 512), 'white').save(out, format='PNG'); return out.getvalue()


@pytest.mark.parametrize('provider,model', [('qwen', 'fictional-editor'),
    ('doubao', 'doubao-seedream-5-0-pro-260628'), ('doubao', 'doubao-seedream-4-0-250828')])
def test_provider_photo_edit_contract_and_download_does_not_forward_token(provider, model):
    seen = []
    raw = picture()
    def handler(request):
        seen.append(request)
        if request.method == 'GET':
            assert 'Authorization' not in request.headers
            return httpx.Response(200, content=raw)
        assert request.headers['Authorization'] == 'Bearer fictional-secret'
        body = json.loads(request.content)
        assert body['model'] == model
        if provider == 'qwen':
            assert request.url.path.endswith('/services/aigc/multimodal-generation/generation')
            assert body['input']['messages'][0]['content'][0]['image'].startswith('data:image/jpeg;base64,')
            assert body['parameters']['n'] == 1
            return httpx.Response(200, json={'output': {'choices': [{'message': {'content': [
                {'image': 'https://dashscope-test.oss-cn-beijing.aliyuncs.com/generated.png?signature=fictional'}]}}]}})
        assert request.url.path.endswith('/images/generations')
        assert body['response_format'] == 'b64_json' and body['image'].startswith('data:image/jpeg;base64,')
        assert body['size'] == '2048x2048' and body['watermark'] is False
        if model == 'doubao-seedream-5-0-pro-260628':
            assert body['output_format'] == 'png'
        else:
            assert 'output_format' not in body
        return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(raw).decode()}]})
    config = settings(provider); config.avatar_image_model = model
    result = asyncio.run(ImageEditor(config, httpx.MockTransport(handler)).edit(b'fictional-photo', 'image/jpeg'))
    with Image.open(BytesIO(result)) as image:
        assert image.mode == 'RGBA' and image.size == (512, 512)
    assert len(seen) == (2 if provider == 'qwen' else 1)


@pytest.mark.parametrize('url', ['http://127.0.0.1/private', 'https://evil.invalid/p',
    'https://dashscope-test.oss-cn-beijing.aliyuncs.com.evil.invalid/x',
    'https://user@dashscope-test.oss-cn-beijing.aliyuncs.com/x'])
def test_qwen_output_url_is_restricted_to_provider_storage(url):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'output': {'choices': [{'message': {'content': [{'image': url}]}}]}})
    with pytest.raises(PipelineError) as error:
        asyncio.run(ImageEditor(settings('qwen'), httpx.MockTransport(handler)).edit(b'photo', 'image/jpeg'))
    assert error.value.code == 'IMAGE_EDIT_FAILED' and len(seen) == 1


def test_timeout_is_unknown_and_does_not_retry_paid_generation():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('fictional-private-provider-error')
    with pytest.raises(PipelineError) as error:
        asyncio.run(ImageEditor(settings('doubao'), httpx.MockTransport(handler)).edit(b'photo', 'image/jpeg'))
    assert error.value.code == 'IMAGE_RESULT_UNKNOWN' and len(calls) == 1
    assert 'private' not in str(error.value)


def test_face_placement_creates_tha3_layout_and_rejects_bad_bounds():
    image = Image.new('RGBA', (400, 600))
    image.paste((255, 128, 20, 255), (100, 100, 200, 200))
    placed = place_face(image, (100, 100, 100, 100))
    with Image.open(BytesIO(placed)) as result:
        assert result.size == (512, 512) and result.mode == 'RGBA'
        assert result.getpixel((256, 142)) == (255, 128, 20, 255)
        assert result.getpixel((0, 0))[3] == 0
    with pytest.raises(ValueError): place_face(image, (-20, 100, 100, 100))
    with pytest.raises(PipelineError): normalize_illustration(b'not-an-image')
