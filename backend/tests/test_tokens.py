import json
from datetime import timedelta
from uuid import uuid4

import pytest

from app.modules.auth.tokens import TokenCodec, decode, digest, encode, new_refresh, refresh_device_name
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7

KEY = "fictional-test-signing-key-" * 3


def test_access_signature_expiry_and_identity():
    codec = TokenCodec(KEY)
    now = utcnow()
    user, session = uuid7(), uuid7()
    token = codec.access(user, session, "演示设备", now)
    assert codec.verify(token, now)["sub"] == str(user)
    assert codec.verify(token, now)["sid"] == str(session)
    with pytest.raises(AppError) as expiry:
        codec.verify(token, now + timedelta(seconds=901))
    assert expiry.value.code == "AUTH_TOKEN_EXPIRED"
    header, body, signature = token.split('.')
    claims = json.loads(decode(body)); claims['sub'] = str(uuid4())
    with pytest.raises(AppError) as forged:
        codec.verify(header + '.' + encode(json.dumps(claims).encode()) + '.' + signature, now)
    assert forged.value.code == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.parametrize("token", ["", "a.b.c", "x" * 4097, "a.b.c.d", "...", "null"], ids=["empty","malformed","oversized","extra-part","empty-parts","literal"])
def test_malformed_bearer_has_uniform_error(token):
    with pytest.raises(AppError) as invalid:
        TokenCodec(KEY).verify(token)
    assert invalid.value.code == "AUTH_INVALID_CREDENTIALS"
    assert token not in invalid.value.message if token else True


def test_refresh_entropy_label_and_hash_only_storage_value():
    a, b = new_refresh("演示设备"), new_refresh("演示设备")
    assert a != b and len(a.split('.')[0]) >= 43
    assert refresh_device_name(a) == "演示设备"
    assert len(digest(a)) == 64 and a not in digest(a)


def test_uuid_version_and_missing_key():
    assert uuid7().version == 7
    with pytest.raises(AppError) as missing:
        TokenCodec("")
    assert missing.value.status_code == 503
