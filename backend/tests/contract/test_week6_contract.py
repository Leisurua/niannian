from pathlib import Path
import yaml

from app.modules.conversation.proactive import PreferenceInput, ConfirmInput
from app.main import app


def test_reviewed_week6_operations_and_conditional_reason_header():
    spec = yaml.safe_load((Path(__file__).resolve().parents[3] / 'docs/openapi.yaml').read_text(encoding='utf-8'))
    schemas = spec['components']['schemas']
    assert set(PreferenceInput.model_fields) == set(schemas['ProactivePreferenceInput']['properties'])
    assert set(ConfirmInput.model_fields) == set(schemas['ProactiveConfirmInput']['properties'])
    for path, method in [('/conversations/{conversation_id}', 'get'), ('/conversations/{conversation_id}/summary', 'post')]:
        reason = spec['paths'][path][method]['parameters'][0]
        assert reason['name'] == 'X-Access-Reason' and reason['in'] == 'header'
        assert reason['schema']['enum'] == ['FAMILY_CHECK_IN', 'FOLLOW_UP']
    ids = {route.operation_id for route in app.routes if getattr(route, 'operation_id', None)}
    assert {'getProactivePreference', 'putProactivePreference', 'confirmProactivePreference', 'pauseProactiveToday'} <= ids
