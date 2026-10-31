"""Configure Beijing family voices locally; never accept API keys on the command line."""
import argparse
from getpass import getpass
from pathlib import Path
import os
import re
import subprocess
import sys

from dotenv import dotenv_values, set_key
import httpx

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(Exception):
    pass


def verify(workspace, key, *, transport=None):
    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', workspace):
        raise ConfigurationError('请填写北京地域业务空间 ID，不是空间名称或网址。')
    if not key or any(char.isspace() for char in key):
        raise ConfigurationError('API Key 为空或包含空白，请重新复制。')
    url = f'https://{workspace}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/customization'
    try:
        with httpx.Client(timeout=20, follow_redirects=False, transport=transport) as client:
            with client.stream('POST', url, headers={'Authorization': 'Bearer ' + key},
                    json={'model': 'voice-enrollment', 'input': {
                        'action': 'list_voice', 'page_index': 0, 'page_size': 1}}) as response:
                if response.status_code in (401, 403):
                    raise ConfigurationError('鉴权未通过：请核对北京地域 Key、业务空间及音色服务访问权限。')
                if response.status_code != 200:
                    raise ConfigurationError(f'百炼返回 HTTP {response.status_code}；未修改本机配置。')
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise ConfigurationError('响应超出限制，无法确认配置。')
                import json
                result = json.loads(data)
                if result.get('code') or not isinstance(result.get('output', {}).get('voice_list'), list):
                    raise ConfigurationError('百炼未返回有效音色列表，请检查服务是否开通。')
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise ConfigurationError('无法连接百炼或响应无效，请检查网络与业务空间 ID。') from None


def configure(env_file, workspace, key, *, transport=None):
    verify(workspace, key, transport=transport)
    # Validation happens before any edit; write the switch last.
    set_key(env_file, 'FAMILY_VOICE_WORKSPACE_ID', workspace)
    set_key(env_file, 'FAMILY_VOICE_API_KEY', key)
    set_key(env_file, 'FAMILY_VOICE_ENABLED', 'true', quote_mode='never')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify existing credentials without editing .env')
    args = parser.parse_args()
    env_file = ROOT / '.env'
    values = {**dotenv_values(env_file), **os.environ}
    workspace = values.get('FAMILY_VOICE_WORKSPACE_ID', '')
    key = values.get('FAMILY_VOICE_API_KEY', '') or values.get('DASHSCOPE_API_KEY', '')
    try:
        if args.check:
            if not workspace or not key:
                raise ConfigurationError('缺少百炼北京地域 API Key 或业务空间 ID；请在本机终端不带 --check 运行本脚本。')
            verify(workspace, key)
            print('百炼音色管理鉴权通过；合成模型权限及音色效果仍需获准录音联调确认。')
            return 0
        if not sys.stdin.isatty():
            raise ConfigurationError('请在本机交互式终端运行；密钥只能隐藏输入，不接受管道或命令行参数。')
        ignored = subprocess.run(['git', 'check-ignore', '--quiet', '.env'], cwd=ROOT, check=False)
        if ignored.returncode != 0:
            raise ConfigurationError('请先确保项目 .env 被 Git 忽略，再配置密钥。')
        print('需要百炼北京地域 API Key 和对应业务空间 ID。密钥输入不回显。')
        workspace = input('业务空间 ID' + ('（回车保留现有值）' if workspace else '') + '：').strip() or workspace
        entered = getpass('API Key' + ('（回车保留现有值）' if key else '') + '：').strip()
        configure(env_file, workspace, entered or key)
        print('已验证并保存到本机 .env，FAMILY_VOICE_ENABLED=true。请以 APP_ENV=dev 重启 API 和普通 worker。')
        print('鉴权检查未上传录音或创建音色；实际合成及效果需本人授权后验证。')
        return 0
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, KeyboardInterrupt, EOFError):
        print('配置未完成。请检查本机文件权限或重新运行。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
