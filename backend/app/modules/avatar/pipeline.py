import asyncio
import base64
from io import BytesIO
import json
import os
import re
from pathlib import Path
import subprocess
from zipfile import ZipFile
from urllib.parse import urlsplit

import httpx
from PIL import Image

PROMPT = """将参考照片中的一位人物绘制为温暖、清晰的二维动漫人物立绘，保留可辨识的脸型、
年龄感、发型、眼镜和服装特征。只画一个人，正面直立，眼睛自然睁开直视前方，嘴巴完全闭合，
中性友好表情。完整头发和肩膀不能裁断，手放低且远离脸部。画出头部与上半身，头部位于画面
上半部中央，四周留白。背景为干净纯白，无场景、文字、标志、棋盘格。线条清楚、柔和上色，
避免皮肤或发型与背景粘连，不添加第二张脸或装饰人像。输出正方形单张图像。"""


class PipelineError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def normalize_illustration(data):
    try:
        with Image.open(BytesIO(data), formats=['PNG', 'JPEG', 'WEBP']) as image:
            if image.width * image.height > 4194304 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError()
            image.load()
            clean = Image.new('RGBA', image.size)
            clean.paste(image.convert('RGBA'))
            out = BytesIO(); clean.save(out, format='PNG')
            return out.getvalue()
    except Exception:
        raise PipelineError('ILLUSTRATION_INVALID') from None


class ImageEditor:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def edit(self, photo, mime):
        s = self.settings
        if not s.avatar_generation_enabled or s.app_env != 'dev':
            raise PipelineError('IMAGE_SERVICE_DISABLED')
        try:
            image = f'data:{mime};base64,' + base64.b64encode(photo).decode('ascii')
            if s.avatar_image_provider == 'qwen':
                path = '/services/aigc/multimodal-generation/generation'
                payload = {'model': s.avatar_image_model, 'input': {'messages': [{'role': 'user',
                    'content': [{'image': image}, {'text': PROMPT}]}]},
                    'parameters': {'n': 1, 'size': '1024*1024', 'prompt_extend': False, 'watermark': False}}
            else:
                path = '/images/generations'
                payload = {'model': s.avatar_image_model, 'image': image, 'prompt': PROMPT,
                    'size': '2048x2048', 'response_format': 'b64_json', 'watermark': False}
                if s.avatar_image_model.startswith(('doubao-seedream-5-0-pro-', 'doubao-seedream-5-0-flash-')):
                    payload['output_format'] = 'png'
            async with httpx.AsyncClient(timeout=s.avatar_image_timeout, follow_redirects=False, transport=self.transport) as client:
                async with client.stream('POST', s.avatar_image_base_url.rstrip('/') + path,
                    headers={'Authorization': 'Bearer ' + s.avatar_image_api_key},
                    json=payload) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 24 * 1024 * 1024:
                            raise ValueError()
                result = json.loads(body)
                if s.avatar_image_provider == 'qwen':
                    url = result['output']['choices'][0]['message']['content'][0]['image']
                    target = urlsplit(url)
                    if (target.scheme != 'https' or target.username or target.password or target.port not in (None, 443)
                            or not re.fullmatch(r'dashscope-[a-z0-9-]+\.oss(?:-accelerate|-cn-[a-z0-9-]+)\.aliyuncs\.com', target.hostname or '')):
                        raise ValueError('Invalid image host')
                    raw = bytearray()
                    async with client.stream('GET', url) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 16 * 1024 * 1024:
                                raise ValueError('Image too large')
                    raw = bytes(raw)
                else:
                    raw = base64.b64decode(result['data'][0]['b64_json'], validate=True)
                    if len(raw) > 16 * 1024 * 1024:
                        raise ValueError('Image too large')
            return await asyncio.to_thread(normalize_illustration, raw)
        except PipelineError:
            raise
        except httpx.TimeoutException:
            raise PipelineError('IMAGE_RESULT_UNKNOWN') from None
        except Exception:
            raise PipelineError('IMAGE_EDIT_FAILED') from None


def check_pack(data):
    if len(data) > 24 * 1024 * 1024:
        raise PipelineError('AVATAR_PACK_INVALID')
    try:
        with ZipFile(BytesIO(data)) as archive:
            expected = {'manifest.json', 'idle.png', 'listening.png', 'thinking.png', 'speaking.png'}
            if len(archive.infolist()) != 5 or set(archive.namelist()) != expected or sum(x.file_size for x in archive.infolist()) > 24 * 1024 * 1024:
                raise ValueError()
            if archive.getinfo('manifest.json').file_size > 8192:
                raise ValueError()
            manifest = json.loads(archive.read('manifest.json'))
            if manifest['format'] != 'niannian-tha3-v1' or manifest['frame_size'] != 256 or manifest['columns'] != 4:
                raise ValueError()
            if not isinstance(manifest.get('credits'), str) or not 1 <= len(manifest['credits']) <= 2048:
                raise ValueError()
            if set(manifest['states']) != {'IDLE', 'LISTENING', 'THINKING', 'SPEAKING'}:
                raise ValueError()
            preview = Image.new('RGBA', (1024, 256))
            for i, phase in enumerate(('IDLE', 'LISTENING', 'THINKING', 'SPEAKING')):
                clip = manifest['states'][phase]
                if clip['file'] != phase.lower() + '.png' or not 1 <= clip['frames'] <= 16 or not 1 <= clip['fps'] <= 15:
                    raise ValueError()
                if archive.getinfo(clip['file']).file_size > 6 * 1024 * 1024:
                    raise ValueError()
                with Image.open(BytesIO(archive.read(clip['file'])), formats=['PNG']) as image:
                    if image.mode != 'RGBA' or image.size != (1024, ((clip['frames'] + 3) // 4) * 256):
                        raise ValueError()
                    image.load()
                    frame = 2 if phase == 'SPEAKING' and clip['frames'] >= 3 else 0
                    preview.paste(image.crop((frame * 256, 0, (frame + 1) * 256, 256)), (i * 256, 0))
            out = BytesIO(); preview.save(out, format='PNG')
            return out.getvalue()
    except PipelineError:
        raise
    except Exception:
        raise PipelineError('AVATAR_PACK_INVALID') from None


class Tha3Renderer:
    def __init__(self, settings):
        self.settings = settings

    async def render(self, illustration):
        s = self.settings
        backend = Path(__file__).resolve().parents[3]
        args = [s.avatar_tha3_python, '-m', 'app.integrations.tha3_renderer', '--stdio',
            '--tha3-root', s.avatar_tha3_root, '--model-dir', s.avatar_tha3_models,
            '--art-credit', 'User-authorized photo stylized by configured image service; AI companion depiction.']
        data = await self._run(args, illustration, backend)
        preview = await asyncio.to_thread(check_pack, data)
        return data, preview

    async def prepare(self, illustration):
        s = self.settings
        backend = Path(__file__).resolve().parents[3]
        return await self._run([s.avatar_tha3_python, '-m', 'app.integrations.avatar_preprocess',
            '--cascade', s.avatar_face_cascade, '--models', s.avatar_rembg_models], illustration, backend, prefix='PREPARE')

    async def _run(self, args, illustration, backend, prefix='THA3'):
        try:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend), 'PYTHONUTF8': '1'},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except Exception:
            raise PipelineError(prefix + '_UNAVAILABLE') from None
        communication = asyncio.create_task(asyncio.to_thread(process.communicate, illustration))
        try:
            data, _ = await asyncio.wait_for(asyncio.shield(communication), timeout=self.settings.avatar_render_timeout)
            if process.returncode != 0:
                raise PipelineError(prefix + '_FAILED')
            if len(data) > 24 * 1024 * 1024:
                raise PipelineError('AVATAR_PACK_INVALID')
            return data
        except TimeoutError:
            raise PipelineError(prefix + '_TIMEOUT') from None
        finally:
            if process.poll() is None:
                process.kill()
            await asyncio.shield(communication)
