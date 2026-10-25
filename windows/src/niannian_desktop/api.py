from __future__ import annotations

import json
import socket
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from uuid import uuid4

APP_VERSION = "0.1.0"


class ClientError(RuntimeError):
    """Base client failure safe to present to a user."""


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
        request = f"，请求编号 {self.request_id}" if self.request_id else ""
        return f"HTTP {self.status} / {self.code}: {self.message}{request}"


def normalize_base_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("请输入服务器地址。")
    if "://" not in candidate:
        candidate = "http://" + candidate
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("服务器地址应类似 http://192.168.1.20:8000。")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError("服务器地址只填写主机和端口，不要附加账号或参数。")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("服务器端口应在 1 到 65535 之间。") from None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("服务器端口应在 1 到 65535 之间。")
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    if path:
        raise ValueError("服务器地址只填写主机和端口，不要附加接口路径。")
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def _json_or_empty(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError("服务器返回了无法识别的数据。") from exc
    if not isinstance(value, dict):
        raise NetworkError("服务器返回格式不符合约定。")
    return value


class ApiClient:
    login_kind = "family"
    default_identifier = "demo-child"
    default_device_name = "Windows 子女端"

    def __init__(self, base_url: str, timeout: float = 6.0):
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.user: dict[str, Any] | None = None
        self.binding: dict[str, Any] | None = None
        self._feature_cache: dict[str, bool] | None = None
        self._request_lock = threading.RLock()
        self._pending_message: tuple[dict[str, Any], str] | None = None
        self.login_device_id = f"windows-{self.login_kind}-login-{uuid4()}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
        idempotency_key: str | None = None,
        access_reason: str | None = None,
    ) -> dict[str, Any]:
        extra = {'access_reason': access_reason} if access_reason is not None else {}
        with self._request_lock:
            try:
                return self._exchange(method, path, body=body, auth=auth, idempotency_key=idempotency_key, **extra)
            except ApiError as exc:
                if not auth or exc.status != 401:
                    raise
                if exc.code != 'AUTH_TOKEN_EXPIRED' or not self.refresh_token:
                    self.clear_session()
                    raise
                try:
                    pair = self._exchange('POST', '/v1/auth/refresh', auth=False,
                                          body={'refresh_token': self.refresh_token})
                    self.access_token, self.refresh_token = pair['access_token'], pair['refresh_token']
                except Exception as refresh_error:
                    self.clear_session()
                    raise ClientError('登录续期未能确认，请重新登录。') from refresh_error
                try:
                    return self._exchange(method, path, body=body, auth=auth, idempotency_key=idempotency_key, **extra)
                except ApiError as retry_error:
                    if retry_error.status == 401:
                        self.clear_session()
                    raise

    def _exchange(self, method, path, *, body=None, auth=True, idempotency_key=None, access_reason=None):
        self._check_optional_api(path)
        headers = {"Accept": "application/json", "User-Agent": f"NianNian-Windows/{APP_VERSION}"}
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
        if access_reason is not None:
            if access_reason not in ('FAMILY_CHECK_IN', 'FOLLOW_UP'):
                raise ClientError('请选择有效的查看理由。')
            headers['X-Access-Reason'] = access_reason
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return _json_or_empty(response.read())
        except HTTPError as exc:
            try:
                payload = _json_or_empty(exc.read())
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

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", auth=False)

    def weather_cities(self, name: str) -> list[dict[str, Any]]:
        return self._request('GET', '/v1/weather/cities?' + urlencode({'q': name.strip()})).get('items', [])

    def weather_current(self, city_id: int) -> dict[str, Any]:
        return self._request('GET', '/v1/weather/current?' + urlencode({'city_id': city_id}))

    def report_subjects(self, family_id: str) -> list[dict[str, Any]]:
        if self.login_kind == 'elder':
            return [self.user] if self.user else []
        items, cursor = [], None
        while True:
            result = self._request('GET', f'/v1/families/{quote(family_id)}/members?limit=100' + ('&cursor=' + quote(cursor) if cursor else ''))
            items.extend(dict(id=row['user_id'], display_name=row.get('display_name') or '长辈')
                for row in result.get('items', []) if row['role'] == 'ELDER' and row['status'] == 'ACTIVE')
            if not result.get('page', {}).get('has_more'):
                return items
            next_cursor = result['page'].get('next_cursor')
            if not next_cursor or next_cursor == cursor:
                raise NetworkError('成员分页未向前推进。')
            cursor = next_cursor

    def weekly_report(self, family_id: str, owner: str, week: str, reason: str | None = None) -> dict[str, Any]:
        return self._request('GET', '/v1/reports/weekly?' + urlencode(dict(family_id=family_id,
            owner_user_id=owner, week_start=week, timezone='Asia/Shanghai')), access_reason=reason)

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
            raise ClientError("当前服务器版本不支持设备或留言功能，请更新后端并运行数据库迁移。")

    def clear_session(self) -> None:
        self.access_token = self.refresh_token = None
        self.user = self.binding = None
        self._pending_message = None

    def logout(self) -> None:
        with self._request_lock:
            try:
                if self.access_token:
                    self._request('POST', '/v1/auth/logout', body={})
            except ApiError as exc:
                if exc.status != 401:
                    raise
            finally:
                self.clear_session()

    def send_text(self, text: str, role: str, priority: str) -> dict[str, Any]:
        clean = text.strip()
        if not clean or len(clean) > 2000:
            raise ClientError('留言需为 1 到 2000 个字符。')
        body = {'destination': {'type': 'FAMILY_ROLE', 'role': role},
                'message_type': 'TEXT', 'priority': priority, 'payload': {'text': clean}}
        if self.binding:
            body['family_id'] = self.binding['family_id']
        with self._request_lock:
            if self._pending_message and self._pending_message[0] != body:
                raise ClientError('上条留言的发送结果尚未确认，请先用原内容重试发送。')
            if not self._pending_message:
                self._pending_message = body, str(uuid4())
            try:
                result = self._request('POST', '/v1/messages', body=body,
                                       idempotency_key=self._pending_message[1])
            except ApiError as exc:
                if 400 <= exc.status < 500 and exc.status not in (408, 429):
                    self._pending_message = None
                raise
            self._pending_message = None
            return result

    def login(self, identifier: str | None = None, *, device_name: str | None = None) -> dict[str, Any]:
        self.clear_session()
        result = self._request(
            "POST",
            "/v1/auth/login",
            auth=False,
            body={
                "credential": {"type": "DEMO", "identifier": identifier or self.default_identifier},
                "device": {
                    "device_id": self.login_device_id,
                    "name": device_name or self.default_device_name,
                    "app_version": APP_VERSION,
                },
            },
        )
        self.access_token = str(result["access_token"])
        self.refresh_token = str(result["refresh_token"])
        self.user = dict(result["user"])
        return result

    def list_families(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v1/families?limit=100").get("items", []))

    def list_messages(self, box: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        items = []
        while True:
            query = urlencode({"box": box, "after_sequence": after_sequence, "limit": 100})
            if self.binding:
                query += '&' + urlencode({'family_id': self.binding['family_id']})
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

    def receive_messages(self) -> list[dict[str, Any]]:
        items = self.list_messages('INBOX')
        for item in items:
            for delivery in item.get('deliveries', []):
                if delivery.get('status') == 'QUEUED':
                    delivery.update(self.acknowledge(str(delivery['id']), 'received'))
        return items

    def acknowledge(self, delivery_id: str, kind: str) -> dict[str, Any]:
        if kind not in ("received", "read"):
            raise ValueError("Unsupported acknowledgement kind")
        return self._request(
            "POST",
            f"/v1/message-deliveries/{quote(delivery_id)}/{kind}",
            body={},
            idempotency_key=str(uuid4()),
        )
