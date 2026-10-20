from __future__ import annotations

import json
import platform
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from uuid import uuid4


APP_VERSION = "0.1.0"


class ClientError(RuntimeError):
    """A failure that can be shown directly in the demonstration UI."""


class NetworkError(ClientError):
    pass


class ApiError(ClientError):
    def __init__(self, status: int, code: str, message: str, request_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id

    def __str__(self) -> str:
        suffix = f"，请求编号 {self.request_id}" if self.request_id else ""
        return f"HTTP {self.status} / {self.code}: {self.message}{suffix}"


def normalize_base_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("请输入服务器地址。")
    if "://" not in candidate:
        candidate = "http://" + candidate
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("服务器地址应类似 http://192.168.1.20:8000。")
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    if path:
        raise ValueError("服务器地址只填写主机和端口，不要附加接口路径。")
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _decode(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError("服务器返回了无法识别的数据。") from exc
    if not isinstance(value, dict):
        raise NetworkError("服务器返回格式不符合约定。")
    return value


class ElderClient:
    def __init__(self, base_url: str, timeout: float = 6.0):
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        self.access_token: str | None = None
        self.user: dict[str, Any] | None = None
        self.binding: dict[str, Any] | None = None
        self._feature_cache: dict[str, bool] | None = None
        self.login_device_id = f"windows-elder-login-{uuid4()}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._check_optional_api(path)
        headers = {"Accept": "application/json", "User-Agent": f"NianNian-Windows-Elder/{APP_VERSION}"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.access_token:
                raise ClientError("尚未登录。")
            headers["Authorization"] = "Bearer " + self.access_token
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return _decode(response.read())
        except HTTPError as exc:
            try:
                payload = _decode(exc.read())
            except ClientError:
                payload = {}
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            raise ApiError(
                exc.code,
                str(error.get("code") or "HTTP_ERROR"),
                str(error.get("message") or exc.reason or "服务器拒绝了请求。"),
                str(payload.get("request_id") or error.get("request_id") or "") or None,
            ) from exc
        except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise NetworkError(f"无法连接 {self.base_url}：{reason}") from exc

    def backend_features(self) -> dict[str, bool]:
        """Inspect the running FastAPI server without modifying any data."""
        if self._feature_cache is None:
            paths = self._request("GET", "/openapi.json", auth=False).get("paths", {})
            if not isinstance(paths, dict):
                raise NetworkError("服务器没有返回有效接口清单。")
            self._feature_cache = {
                "devices": "/v1/devices/register" in paths and "/v1/devices" in paths,
                "messages": "/v1/messages" in paths
                    and any(p.startswith("/v1/messages/{") for p in paths)
                    and any(p.startswith("/v1/message-deliveries/") and p.endswith("/received") for p in paths)
                    and any(p.startswith("/v1/message-deliveries/") and p.endswith("/read") for p in paths),
            }
        return dict(self._feature_cache)

    def _check_optional_api(self, path: str) -> None:
        feature = ("devices" if path.startswith("/v1/devices") else
                   "messages" if path.startswith(("/v1/messages", "/v1/message-deliveries")) else None)
        if feature and not self.backend_features()[feature]:
            raise ClientError("当前 main 服务器尚未提供设备注册或消息收发 API，"
                              "现可使用登录、家庭和邀请功能；消息功能仍待服务端实现。")

    def tcp_check(self) -> tuple[str, int]:
        parsed = urlparse(self.base_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        started = time.perf_counter()
        try:
            with socket.create_connection((parsed.hostname or "", port), timeout=self.timeout):
                pass
        except OSError as exc:
            raise NetworkError(f"TCP 无法到达 {parsed.hostname}:{port}：{exc}") from exc
        return f"{parsed.hostname}:{port}", round((time.perf_counter() - started) * 1000)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", auth=False)

    def login(self) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/v1/auth/login",
            auth=False,
            body={
                "credential": {"type": "DEMO", "identifier": "demo-elder"},
                "device": {
                    "device_id": self.login_device_id,
                    "name": "Windows 老人演示端",
                    "app_version": APP_VERSION,
                },
            },
        )
        self.access_token = str(result["access_token"])
        self.user = dict(result["user"])
        return result

    def list_families(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v1/families?limit=100").get("items", []))

    def accept_invitation(self, token: str) -> dict[str, Any]:
        clean = token.strip()
        if not clean:
            raise ClientError("请粘贴子女端生成的邀请令牌。")
        return self._request(
            "POST",
            f"/v1/family-invitations/{quote(clean, safe='')}/accept",
            body={"confirm_identity": True, "requested_display_name": "演示老人"},
        )

    def register_device(self, family_id: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/v1/devices/register",
            body={
                "device_id": f"windows-elder-{uuid4()}",
                "device_type": "OTHER",
                "client_kind": "ELDER_MOBILE",
                "family_id": family_id,
                "app_version": APP_VERSION,
                "os_version": platform.platform(),
                "capabilities": {
                    "desktop_demo": True,
                    "large_text": True,
                    "rest_polling": True,
                },
            },
            idempotency_key=str(uuid4()),
        )
        self.binding = result
        return result

    def list_messages(self, box: str) -> list[dict[str, Any]]:
        items = []
        after_sequence = 0
        while True:
            query = urlencode({"box": box, "after_sequence": after_sequence, "limit": 100})
            result = self._request("GET", "/v1/messages?" + query)
            items.extend(result.get("items", []))
            page = result.get("page", {})
            if not page.get("has_more"):
                return items
            try:
                next_sequence = int(page["next_cursor"])
            except (KeyError, TypeError, ValueError) as exc:
                raise NetworkError("服务器返回了无效的消息分页信息。") from exc
            if next_sequence <= after_sequence:
                raise NetworkError("服务器返回的消息分页未向前推进。")
            after_sequence = next_sequence

    def acknowledge(self, delivery_id: str, kind: str) -> dict[str, Any]:
        if kind not in ("received", "read"):
            raise ValueError("Unsupported acknowledgement kind")
        return self._request(
            "POST",
            f"/v1/message-deliveries/{quote(delivery_id)}/{kind}",
            body={},
            idempotency_key=str(uuid4()),
        )

    def reply_to_children(self, text: str, *, important: bool = False) -> dict[str, Any]:
        clean = text.strip()
        if not clean:
            raise ClientError("回复内容不能为空。")
        return self._request(
            "POST",
            "/v1/messages",
            body={
                "destination": {"type": "FAMILY_ROLE", "role": "CHILD"},
                "message_type": "TEXT",
                "priority": "IMPORTANT" if important else "NORMAL",
                "payload": {"text": clean},
            },
            idempotency_key=str(uuid4()),
        )
