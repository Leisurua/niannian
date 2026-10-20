import re
from pathlib import Path

import pytest
import yaml
from app.main import app
from app.platform.errors import AppError
from app.platform.resource_access import expected_version
from fastapi.testclient import TestClient


def test_implemented_rest_operations_are_documented():
    spec = yaml.safe_load((Path(__file__).resolve().parents[2] / 'docs/openapi.yaml').read_text(encoding='utf-8'))
    documented = {re.sub(r'\{[^}]+\}', '{}', path): methods for path, methods in spec['paths'].items()}
    for path, operations in app.openapi()['paths'].items():
        if not path.startswith('/v1/'):
            continue
        for method, operation in operations.items():
            normalized = re.sub(r'\{[^}]+\}', '{}', path.removeprefix('/v1'))
            assert documented[normalized][method]['operationId'] == operation['operationId']


def test_login_requires_credentials():
    response = TestClient(app).post('/v1/auth/login', json={})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'


@pytest.mark.parametrize('allow_zero', [False, True])
def test_if_match_keeps_optimistic_versions_strict(allow_zero):
    for header, version in [('1', 1), ('"1"', 1), ('123', 123)]:
        assert expected_version(header, allow_zero=allow_zero) == version
    if allow_zero:
        assert expected_version('0', allow_zero=True) == 0
        assert expected_version('"0"', allow_zero=True) == 0
    invalid = ['', '01', '"01"', '-1', '1.0', 'W/"1"', '*', '"1', '1"', '1' * 65]
    if not allow_zero:
        invalid += ['0', '"0"']
    for header in invalid:
        with pytest.raises(AppError) as caught:
            expected_version(header, allow_zero=allow_zero)
        assert caught.value.code == 'ETAG_MISMATCH'
