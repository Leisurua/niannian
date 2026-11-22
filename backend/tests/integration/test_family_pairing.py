from datetime import datetime, timedelta
import re
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.platform.config import get_settings
from app.platform.identifiers import utcnow
from backend.tests.support import URL, login, post

pytestmark = pytest.mark.skipif(not URL, reason="Set TEST_DATABASE_URL to run PostgreSQL integration tests")


def test_personal_accounts_join_with_a_one_time_family_code(system, monkeypatch):
    client, engine, _, _ = system
    _, demo_headers = login(client, "demo-child")
    monkeypatch.setenv("AUTH_MODE", "password")
    get_settings.cache_clear()

    device = {"device_id": str(uuid4()), "name": "虚构手机", "app_version": "0.1.0"}
    assert client.get("/v1/me", headers=demo_headers).status_code == 401
    assert client.post("/v1/auth/login", json={
        "credential": {"type": "DEMO", "identifier": "demo-child"}, "device": device,
    }).status_code == 401

    password = "虚构pass42"

    def register(username, display_name, password=password):
        return client.post("/v1/auth/register", json={
            "username": username, "password": password, "display_name": display_name, "device": device,
        })

    def headers(result):
        assert result.status_code == 201
        return {"Authorization": "Bearer " + result.json()["access_token"]}

    assert register("short_pairing", "虚构短密码", password[:-1]).status_code == 422
    child = register("child_pairing", "虚构子女", "fictional pairing test password")
    elder = register("elder_pairing", "虚构长辈")
    outsider = register("other_pairing", "虚构其他家庭")
    ch, eh, oh = map(headers, (child, elder, outsider))
    assert len({account.json()["user"]["id"] for account in (child, elder, outsider)}) == 3
    assert register("CHILD_PAIRING", "另一个称呼").status_code == 409
    assert "password" not in elder.text and "username" not in elder.text
    with engine.connect() as connection:
        hashes = connection.execute(text('SELECT password_hash FROM "user" WHERE username IS NOT NULL')).scalars().all()
        assert len(set(hashes)) == 3 and all(value.startswith("pbkdf2_sha256$600000$") for value in hashes)

    family = post(client, "/v1/families", ch, {"name": "虚构配对家庭"})
    assert family.status_code == 201
    family_id = family.json()["id"]
    invitations = f"/v1/families/{family_id}/invitations"
    now = utcnow()
    body = {"target_role": "ELDER", "expires_at": (now + timedelta(hours=1)).isoformat(), "max_usage": 3}
    key = str(uuid4())
    invitation = post(client, invitations, ch, body, key)
    assert invitation.status_code == 201
    code = invitation.json()["token"]
    assert re.fullmatch(r"[A-Z2-7]{8}", code) and not code.isalpha() and not code.isdigit()
    assert datetime.fromisoformat(invitation.json()["expires_at"]) < now + timedelta(minutes=11)
    assert post(client, invitations, ch, body, key).json()["token"] == code

    formatted = "-".join(code[index:index + 4] for index in range(0, len(code), 4)).lower()
    path = f"/v1/family-invitations/{formatted}/accept"
    assert client.post(path, headers=eh, json={"confirm_identity": True}).status_code == 409
    preview = client.post(path, headers=eh, json={})
    assert preview.status_code == 200
    assert preview.json()["status"] == "PENDING" and preview.json()["inviter_display_name"] == "虚构子女"
    assert client.get(f"/v1/families/{family_id}", headers=eh).status_code == 404
    assert client.post(path, headers=oh, json={}).status_code == 404
    for _ in range(2):
        joined = client.post(path, headers=eh, json={"confirm_identity": True})
        assert joined.status_code == 200 and joined.json()["status"] == "ACTIVE"
        assert joined.json()["permission_codes"] == []
    assert client.get(f"/v1/families/{family_id}", headers=eh).status_code == 200
    assert post(client, invitations, eh, body).status_code == 403
    assert client.get(f"/v1/families/{family_id}", headers=oh).status_code == 404
    assert client.get(f"/v1/consents?family_id={family_id}", headers=eh).json()["items"] == []

    assert client.post("/v1/auth/logout", headers=eh).status_code == 204
    sign_in = {"credential": {"type": "PASSWORD", "identifier": " ELDER_PAIRING ", "proof": "incorrect"},
        "device": {**device, "device_id": str(uuid4())}}
    assert client.post("/v1/auth/login", json=sign_in).status_code == 401
    sign_in["credential"]["proof"] = password
    signed_in = client.post("/v1/auth/login", json=sign_in)
    assert signed_in.json()["user"]["id"] == elder.json()["user"]["id"]
    assert client.get(f"/v1/families/{family_id}", headers=headers(signed_in)).status_code == 200
    for _ in range(9):
        assert client.post(path, headers=oh, json={}).status_code == 404
    assert client.post(path, headers=oh, json={}).status_code == 429
