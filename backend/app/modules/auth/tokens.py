import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime
from uuid import UUID

from app.platform.errors import AppError
from app.platform.identifiers import utcnow


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid encoding")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class TokenCodec:
    def __init__(self, key: str, access_seconds: int = 900):
        if len(key) < 32:
            raise AppError("PROVIDER_TEMPORARILY_UNAVAILABLE", "请先配置服务端登录签名密钥。", 503)
        self._key = key.encode()
        self.access_seconds = access_seconds

    def access(self, user_id: UUID, session_id: UUID, device_name: str, now: datetime | None = None) -> str:
        stamp = int((now or utcnow()).timestamp())
        header = encode(b'{"alg":"HS256","typ":"JWT"}')
        claims = {"sub": str(user_id), "sid": str(session_id), "aud": "niannian-access",
                  "iat": stamp, "exp": stamp + self.access_seconds, "dn": device_name}
        body = encode(json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode())
        signing = f"{header}.{body}"
        return signing + "." + encode(hmac.digest(self._key, signing.encode(), "sha256"))

    def verify(self, token: str, now: datetime | None = None) -> dict:
        try:
            if not token or len(token) > 4096:
                raise ValueError()
            header, body, signature = token.split(".")
            expected = hmac.digest(self._key, f"{header}.{body}".encode(), "sha256")
            if not hmac.compare_digest(decode(signature), expected):
                raise ValueError()
            if json.loads(decode(header)) != {"alg": "HS256", "typ": "JWT"}:
                raise ValueError()
            claims = json.loads(decode(body))
            if claims.get("aud") != "niannian-access" or type(claims.get("exp")) is not int:
                raise ValueError()
            if type(claims.get("iat")) is not int or claims["iat"] > int((now or utcnow()).timestamp()) + 30:
                raise ValueError()
            UUID(claims["sub"])
            UUID(claims["sid"])
            if not isinstance(claims.get("dn"), str) or len(claims["dn"]) > 120:
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
            raise AppError("AUTH_INVALID_CREDENTIALS", "登录凭证无效，请重新登录。", 401) from None
        if claims["exp"] <= int((now or utcnow()).timestamp()):
            raise AppError("AUTH_TOKEN_EXPIRED", "登录已过期，请刷新或重新登录。", 401)
        return claims

    def opaque(self, purpose: str, value: str) -> str:
        return encode(hmac.digest(self._key, (purpose + ":" + value).encode(), "sha256"))


def new_refresh(device_name: str) -> str:
    return secrets.token_urlsafe(32) + "." + encode(device_name.encode())


def refresh_device_name(token: str) -> str:
    try:
        name = decode(token.split(".")[1]).decode()
        if len(name) > 120:
            raise ValueError()
        return name
    except (ValueError, IndexError, UnicodeError):
        raise AppError("AUTH_INVALID_CREDENTIALS", "登录凭证无效，请重新登录。", 401) from None
