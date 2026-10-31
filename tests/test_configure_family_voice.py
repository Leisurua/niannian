import httpx
import pytest
from dotenv import dotenv_values
from scripts.configure_family_voice import ConfigurationError, configure


def test_valid_credentials_enable_only_after_read_only_probe(tmp_path):
    env = tmp_path / '.env'
    env.write_text('LLM_PROVIDER=mock\nFAMILY_VOICE_ENABLED=false\n', encoding='utf-8')
    def handle(request):
        import json
        assert request.url.host == 'fictional.cn-beijing.maas.aliyuncs.com'
        assert json.loads(request.content)['input']['action'] == 'list_voice'
        return httpx.Response(200, json={'output': {'voice_list': []}})
    configure(env, 'fictional', 'fictional-key', transport=httpx.MockTransport(handle))
    values = dotenv_values(env)
    assert values['LLM_PROVIDER'] == 'mock'
    assert values['FAMILY_VOICE_ENABLED'] == 'true'
    assert values['FAMILY_VOICE_API_KEY'] == 'fictional-key'


@pytest.mark.parametrize('status', [401, 403, 500])
def test_failed_probe_preserves_existing_configuration(tmp_path, status):
    env = tmp_path / '.env'
    original = 'FAMILY_VOICE_ENABLED=false\n'
    env.write_text(original, encoding='utf-8')
    with pytest.raises(ConfigurationError) as error:
        configure(env, 'fictional', 'fictional-key', transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={'message': 'secret-provider-detail'})))
    assert env.read_text(encoding='utf-8') == original
    assert 'secret-provider-detail' not in str(error.value)


def test_rejects_workspace_url_without_network(tmp_path):
    with pytest.raises(ConfigurationError):
        configure(tmp_path / '.env', 'https://untrusted.invalid/', 'fictional-key')
    assert not (tmp_path / '.env').exists()
