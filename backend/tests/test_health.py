from app.main import app
from fastapi.testclient import TestClient


def test_health_endpoint_returns_environment_and_request_id() -> None:
    response = TestClient(app).get("/health", headers={"X-Request-ID": "test-health-01"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["request_id"] == "test-health-01"
    assert response.headers["x-request-id"] == "test-health-01"


def test_live_health_has_the_legacy_contract() -> None:
    response = TestClient(app).get('/health/live', headers={'X-Request-ID': 'test-live-01'})

    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert response.json()['request_id'] == 'test-live-01'


def test_metrics_exposes_only_bounded_operational_series(monkeypatch) -> None:
    async def snapshot(*_):
        return False, {name: {'status': 'unavailable'} for name in (
            'api', 'database', 'migrations', 'storage', 'worker')} | {'tasks': {'status': 'unknown'}}

    monkeypatch.setattr('app.platform.health.readiness', snapshot)
    response = TestClient(app).get('/metrics')

    assert response.status_code == 200
    assert 'nianian_http_requests_total' in response.text
    assert 'nianian_http_errors_total' in response.text
    assert 'nianian_http_request_duration_seconds_sum' in response.text
    assert 'nianian_ready 0' in response.text
    assert 'request_id' not in response.text


def test_phone_like_request_id_is_replaced() -> None:
    phone_like = "1" + "3" * 10
    response = TestClient(app).get("/health", headers={"X-Request-ID": phone_like})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != phone_like
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_credential_shaped_request_id_is_replaced() -> None:
    credential = "sk-" + "A" * 24
    response = TestClient(app).get("/health", headers={"X-Request-ID": credential})
    assert response.status_code == 200
    assert response.headers["x-request-id"] != credential
    assert response.json()["request_id"] == response.headers["x-request-id"]
