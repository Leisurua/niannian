import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.platform.models import WEEK2_MODELS


def test_week2_models_follow_frozen_column_inventory():
    dictionary = (Path(__file__).resolve().parents[3] / "docs/data-dictionary.md").read_text(encoding="utf-8")
    for model in WEEK2_MODELS:
        section = re.search(r"^## \d+\. " + model.__tablename__ + r"\n(.*?)(?=^## |\Z)", dictionary, re.M | re.S)[1]
        columns = set(re.findall(r"^\| ([a-z][a-z0-9_]*) \|", section, re.M))
        assert set(model.__table__.columns.keys()) == columns


def test_login_contract_is_routed_and_rejects_missing_fields():
    response = TestClient(app).post('/v1/auth/login', json={})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
