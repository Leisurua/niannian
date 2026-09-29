from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_environment_and_request_id() -> None:
    response = TestClient(app).get("/health", headers={"X-Request-ID": "test-health-01"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["request_id"] == "test-health-01"
    assert response.headers["x-request-id"] == "test-health-01"


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
