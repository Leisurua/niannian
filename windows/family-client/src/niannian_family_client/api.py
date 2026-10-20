from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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


@dataclass
class ProbeStep:
    name: str
    ok: bool
    detail: str
    duration_ms: int | None = None


@dataclass
class ProbeReport:
    steps: list[ProbeStep] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(step.ok for step in self.steps)

    def add(self, name: str, detail: str, started: float | None = None) -> None:
        elapsed = round((time.perf_counter() - started) * 1000) if started is not None else None
        self.steps.append(ProbeStep(name, True, detail, elapsed))

    def fail(self, name: str, detail: str, started: float | None = None) -> None:
        elapsed = round((time.perf_counter() - started) * 1000) if started is not None else None
        self.steps.append(ProbeStep(name, False, detail, elapsed))

    def render(self) -> str:
        lines = ["端到端结果：" + ("通过" if self.ok else "未通过")]
        for index, step in enumerate(self.steps, 1):
            elapsed = f"（{step.duration_ms} ms）" if step.duration_ms is not None else ""
            lines.append(f"{index}. {'通过' if step.ok else '失败'}  {step.name}{elapsed}\n   {step.detail}")
        return "\n".join(lines)


class NianNianClient:
    def __init__(self, base_url: str, timeout: float = 6.0):
        self.base_url = normalize_base_url(base_url)
        self.timeout = timeout
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.user: dict[str, Any] | None = None
        self.binding: dict[str, Any] | None = None
        self.login_device_id = f"windows-family-login-{uuid4()}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
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

    def login(self, identifier: str = "demo-child", *, device_name: str = "Windows 子女端") -> dict[str, Any]:
        result = self._request(
            "POST",
            "/v1/auth/login",
            auth=False,
            body={
                "credential": {"type": "DEMO", "identifier": identifier},
                "device": {
                    "device_id": self.login_device_id,
                    "name": device_name,
                    "app_version": APP_VERSION,
                },
            },
        )
        self.access_token = str(result["access_token"])
        self.refresh_token = str(result["refresh_token"])
        self.user = dict(result["user"])
        return result

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/v1/me")

    def list_families(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v1/families?limit=100").get("items", []))

    def create_family(self, name: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/families",
            body={"name": name.strip()},
            idempotency_key=str(uuid4()),
        )

    def create_invitation(self, family_id: str, role: str = "ELDER") -> dict[str, Any]:
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        return self._request(
            "POST",
            f"/v1/families/{quote(family_id)}/invitations",
            body={"target_role": role, "expires_at": expires.isoformat(), "max_usage": 1},
            idempotency_key=str(uuid4()),
        )

    def accept_invitation(self, token: str, display_name: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"confirm_identity": True}
        if display_name:
            body["requested_display_name"] = display_name
        return self._request("POST", f"/v1/family-invitations/{quote(token, safe='')}/accept", body=body)

    def register_family_device(self, family_id: str) -> dict[str, Any]:
        device_id = f"windows-family-{uuid4()}"
        result = self._request(
            "POST",
            "/v1/devices/register",
            body={
                "device_id": device_id,
                "device_type": "OTHER",
                "client_kind": "FAMILY_MOBILE",
                "family_id": family_id,
                "app_version": APP_VERSION,
                "os_version": platform.platform(),
                "capabilities": {"desktop": True, "rest_polling": True},
            },
            idempotency_key=str(uuid4()),
        )
        self.binding = result
        return result

    def register_elder_test_device(self, family_id: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/v1/devices/register",
            body={
                "device_id": f"windows-e2e-elder-{uuid4()}",
                "device_type": "OTHER",
                "client_kind": "ELDER_MOBILE",
                "family_id": family_id,
                "app_version": APP_VERSION,
                "os_version": "Windows E2E fictional elder",
                "capabilities": {"e2e_probe": True},
            },
            idempotency_key=str(uuid4()),
        )
        self.binding = result
        return result

    def list_devices(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v1/devices?limit=100").get("items", []))

    def send_text_to_role(self, text: str, role: str = "ELDER", priority: str = "NORMAL") -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/messages",
            body={
                "destination": {"type": "FAMILY_ROLE", "role": role},
                "message_type": "TEXT",
                "priority": priority,
                "payload": {"text": text.strip()},
            },
            idempotency_key=str(uuid4()),
        )

    def list_messages(self, box: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        items = []
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

    def message(self, message_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/messages/{quote(message_id)}")


def run_e2e_probe(base_url: str) -> ProbeReport:
    """Create fictional endpoints and prove server-mediated delivery and read receipt."""
    report = ProbeReport()
    child = NianNianClient(base_url)
    elder = NianNianClient(base_url)
    current_name = "初始化"
    started = time.perf_counter()
    try:
        current_name = "TCP 连接"
        endpoint, elapsed = child.tcp_check()
        report.steps.append(ProbeStep(current_name, True, f"已连接 {endpoint}", elapsed))

        current_name, started = "服务健康检查", time.perf_counter()
        health = child.health()
        if health.get("status") != "ok":
            raise ClientError("健康接口未返回 status=ok。")
        report.add(current_name, f"environment={health.get('environment', 'unknown')}", started)

        current_name, started = "双账号登录", time.perf_counter()
        child.login("demo-child", device_name="Windows E2E 虚构子女端")
        elder.login("demo-elder", device_name="Windows E2E 虚构老人端")
        report.add(current_name, "demo-child 与 demo-elder 均取得会话", started)

        current_name, started = "家庭关系", time.perf_counter()
        family = child.create_family("Windows 联机验收（虚构）")
        invitation = child.create_invitation(str(family["id"]), "ELDER")
        elder.accept_invitation(str(invitation["token"]), "验收老人")
        report.add(current_name, "已创建虚构家庭并让老人账号确认加入", started)

        current_name, started = "设备注册", time.perf_counter()
        child_device = child.register_family_device(str(family["id"]))
        elder_device = elder.register_elder_test_device(str(family["id"]))
        report.add(current_name, f"子女端 {child_device['id']}；老人端 {elder_device['id']}", started)

        current_name, started = "消息发送与接收", time.perf_counter()
        sent = child.send_text_to_role("念念 Windows 端到端联机测试", "ELDER")
        if len(sent.get("deliveries", [])) != 1:
            raise ClientError(f"预期 1 个老人端投递，实际 {len(sent.get('deliveries', []))} 个。")
        inbox = elder.list_messages("INBOX")
        received = next((item for item in inbox if item.get("id") == sent.get("id")), None)
        if received is None:
            raise ClientError("老人端收件箱未找到刚发送的消息。")
        delivery_id = str(sent["deliveries"][0]["id"])
        report.add(current_name, f"消息 {sent['id']} 已进入老人端收件箱", started)

        current_name, started = "接收与已读回执", time.perf_counter()
        elder.acknowledge(delivery_id, "received")
        elder.acknowledge(delivery_id, "read")
        final = child.message(str(sent["id"]))
        statuses = [item.get("status") for item in final.get("deliveries", [])]
        if statuses != ["READ"]:
            raise ClientError(f"子女端看到的最终回执不是 READ：{statuses}")
        report.add(current_name, "子女端已确认老人端回执为 READ", started)
    except ClientError as exc:
        report.fail(current_name, str(exc), started)
    except (KeyError, TypeError, ValueError) as exc:
        report.fail(current_name, f"服务响应缺少预期字段：{exc}", started)
    return report
