from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest
from unittest.mock import patch

from niannian_family_client.api import ApiError, ClientError, NianNianClient, normalize_base_url, run_e2e_probe


class Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *_args):
        return

    def _reply(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        Handler.requests.append({"method": "GET", "path": self.path, "authorization": self.headers.get("Authorization")})
        if self.path == "/health":
            self._reply(200, {"status": "ok", "environment": "test", "request_id": "health-1"})
        elif self.path == "/openapi.json":
            self._reply(200, {"paths": {"/v1/auth/login": {}, "/v1/families": {}}})
        elif self.path.startswith("/v1/families"):
            self._reply(200, {"items": [{"id": "family-1", "name": "测试家庭"}]})
        else:
            self._reply(404, {"error": {"code": "NOT_FOUND", "message": "不存在"}, "request_id": "r404"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        Handler.requests.append({
            "method": "POST", "path": self.path, "authorization": self.headers.get("Authorization"),
            "idempotency": self.headers.get("Idempotency-Key"), "body": body,
        })
        if self.path == "/v1/auth/login":
            self._reply(201, {
                "access_token": "access-test", "refresh_token": "refresh-test",
                "user": {"id": "user-1", "display_name": "演示子女"},
            })
        elif self.path == "/v1/families":
            self._reply(409, {"error": {"code": "FAMILY_CONFLICT", "message": "重复家庭"}, "request_id": "req-409"})
        else:
            self._reply(201, {})


class ApiClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        Handler.requests.clear()

    def test_normalize_server_url(self):
        self.assertEqual(normalize_base_url("127.0.0.1:8000/v1/"), "http://127.0.0.1:8000")
        with self.assertRaises(ValueError):
            normalize_base_url("ftp://example.invalid")
        with self.assertRaises(ValueError):
            normalize_base_url("http://localhost:8000/extra")

    def test_health_and_login_use_contract(self):
        client = NianNianClient(self.url)
        self.assertEqual(client.health()["status"], "ok")
        result = client.login()
        self.assertEqual(result["user"]["display_name"], "演示子女")
        login = Handler.requests[-1]
        self.assertEqual(login["body"]["credential"], {"type": "DEMO", "identifier": "demo-child"})
        self.assertEqual(login["body"]["device"]["app_version"], "0.1.0")

    def test_authenticated_request_has_bearer(self):
        client = NianNianClient(self.url)
        client.login()
        self.assertEqual(client.list_families()[0]["id"], "family-1")
        self.assertEqual(Handler.requests[-1]["authorization"], "Bearer access-test")

    def test_unsupported_main_messages_are_blocked_before_post(self):
        client = NianNianClient(self.url)
        client.login()
        self.assertEqual(client.backend_features(), {"devices": False, "messages": False})
        before = len(Handler.requests)
        with self.assertRaises(ClientError):
            client.send_text_to_role("虚构文本")
        self.assertEqual(len(Handler.requests), before)

    def test_api_error_is_human_readable(self):
        client = NianNianClient(self.url)
        client.login()
        with self.assertRaises(ApiError) as caught:
            client.create_family("重复")
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.code, "FAMILY_CONFLICT")
        self.assertIn("req-409", str(caught.exception))


class FakeProbeClient:
    instances = 0
    read = False

    def __init__(self, _base_url):
        self.index = FakeProbeClient.instances
        FakeProbeClient.instances += 1

    def tcp_check(self):
        return "127.0.0.1:8000", 1

    def health(self):
        return {"status": "ok", "environment": "test"}

    def login(self, *_args, **_kwargs):
        return {"user": {"id": f"user-{self.index}"}}

    def backend_features(self):
        return {"devices": True, "messages": True}

    def create_family(self, _name):
        return {"id": "family-1"}

    def create_invitation(self, _family_id, _role):
        return {"token": "fictional-invitation-token"}

    def accept_invitation(self, *_args):
        return {"status": "ACTIVE"}

    def register_family_device(self, _family_id):
        return {"id": "child-device"}

    def register_elder_test_device(self, _family_id):
        return {"id": "elder-device"}

    def send_text_to_role(self, *_args):
        return {"id": "message-1", "deliveries": [{"id": "delivery-1", "status": "QUEUED"}]}

    def list_messages(self, _box):
        return [{"id": "message-1"}]

    def acknowledge(self, _delivery_id, kind):
        if kind == "read":
            FakeProbeClient.read = True
        return {"status": kind.upper()}

    def message(self, _message_id):
        status = "READ" if FakeProbeClient.read else "QUEUED"
        return {"deliveries": [{"status": status}]}


class EndToEndProbeTests(unittest.TestCase):
    def test_probe_requires_final_read_receipt(self):
        FakeProbeClient.instances = 0
        FakeProbeClient.read = False
        with patch("niannian_family_client.api.NianNianClient", FakeProbeClient):
            report = run_e2e_probe("http://127.0.0.1:8000")
        self.assertTrue(report.ok, report.render())
        self.assertEqual(report.steps[-1].name, "接收与已读回执")
        self.assertIn("READ", report.steps[-1].detail)


if __name__ == "__main__":
    unittest.main()
