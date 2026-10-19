from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest

from niannian_elder_demo.api import ApiError, ElderClient, normalize_base_url


class Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *_args):
        return

    def _reply(self, status: int, payload: dict):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        Handler.requests.append({"method": "GET", "path": self.path, "auth": self.headers.get("Authorization")})
        if self.path == "/health":
            self._reply(200, {"status": "ok", "environment": "test"})
        elif self.path.startswith("/v1/families"):
            self._reply(200, {"items": [{"id": "family-1", "name": "演示家庭", "member_status": "ACTIVE"}]})
        elif self.path.startswith("/v1/messages"):
            self._reply(200, {"items": [{
                "id": "message-1", "payload": {"text": "记得吃饭"},
                "deliveries": [{"id": "delivery-1", "status": "QUEUED"}],
            }]})
        else:
            self._reply(404, {"error": {"code": "NOT_FOUND", "message": "不存在"}, "request_id": "req-404"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        Handler.requests.append({
            "method": "POST",
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "idempotency": self.headers.get("Idempotency-Key"),
            "body": body,
        })
        if self.path == "/v1/auth/login":
            self._reply(201, {
                "access_token": "elder-access",
                "refresh_token": "elder-refresh",
                "user": {"id": "elder-1", "display_name": "演示老人"},
            })
        elif self.path.endswith("/accept"):
            self._reply(200, {"family_id": "family-1", "role": "ELDER", "status": "ACTIVE"})
        elif self.path == "/v1/devices/register":
            self._reply(201, {"id": "device-1", "family_id": "family-1", "client_kind": "ELDER_MOBILE"})
        elif self.path == "/v1/messages":
            self._reply(201, {"id": "reply-1", "deliveries": [{"id": "delivery-child", "status": "QUEUED"}]})
        elif "/message-deliveries/" in self.path:
            self._reply(200, {"id": "delivery-1", "status": "READ" if self.path.endswith("/read") else "RECEIVED"})
        else:
            self._reply(409, {"error": {"code": "CONFLICT", "message": "状态冲突"}, "request_id": "req-409"})


class ElderClientTests(unittest.TestCase):
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

    def test_normalize_url(self):
        self.assertEqual(normalize_base_url("127.0.0.1:8000/v1/"), "http://127.0.0.1:8000")
        with self.assertRaises(ValueError):
            normalize_base_url("http://localhost:8000/not-api")

    def test_login_uses_demo_elder_contract(self):
        client = ElderClient(self.url)
        client.login()
        request = Handler.requests[-1]
        self.assertEqual(request["body"]["credential"], {"type": "DEMO", "identifier": "demo-elder"})
        self.assertEqual(request["body"]["device"]["name"], "Windows 老人演示端")

    def test_invitation_and_device_registration(self):
        client = ElderClient(self.url)
        client.login()
        accepted = client.accept_invitation("fictional-token-123456")
        self.assertEqual(accepted["role"], "ELDER")
        binding = client.register_device("family-1")
        self.assertEqual(binding["client_kind"], "ELDER_MOBILE")
        registration = next(item for item in Handler.requests if item["path"] == "/v1/devices/register")
        self.assertEqual(registration["body"]["device_type"], "OTHER")
        self.assertTrue(registration["idempotency"])

    def test_receive_acknowledge_and_reply(self):
        client = ElderClient(self.url)
        client.login()
        client.register_device("family-1")
        inbox = client.list_messages("INBOX")
        self.assertEqual(inbox[0]["payload"]["text"], "记得吃饭")
        self.assertEqual(client.acknowledge("delivery-1", "received")["status"], "RECEIVED")
        self.assertEqual(client.acknowledge("delivery-1", "read")["status"], "READ")
        reply = client.reply_to_children("请给我打电话", important=True)
        self.assertEqual(len(reply["deliveries"]), 1)
        sent = Handler.requests[-1]
        self.assertEqual(sent["body"]["destination"], {"type": "FAMILY_ROLE", "role": "CHILD"})
        self.assertEqual(sent["body"]["priority"], "IMPORTANT")


if __name__ == "__main__":
    unittest.main()
