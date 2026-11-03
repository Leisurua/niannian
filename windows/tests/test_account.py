import io
import json
import secrets
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from zipfile import ZipFile

from niannian_desktop.account import receipt_text
from niannian_desktop.api import ApiClient, ClientError


class AccountTransportTest(unittest.TestCase):
    def test_export_and_lost_deletion_reply_recovery(self):
        token = secrets.token_urlsafe(32)
        calls = []
        archive = io.BytesIO()
        with ZipFile(archive, 'w') as zip_file:
            zip_file.writestr('account.json', '{"fictional":true}')

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, content_type, body):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                calls.append((self.path, self.headers.get('Authorization'), None))
                self.reply(200, 'application/zip', archive.getvalue())

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path, self.headers.get('Authorization'), body))
                if self.path == '/v1/me/deletion':
                    # Simulate committed deletion followed by loss of the response.
                    self.close_connection = True
                    return
                receipt = dict(status='PENDING', local_status='ERASED', backup={'status': 'REQUIRES_OPERATOR'},
                    providers=[{'provider': 'fictional', 'status': 'REQUIRES_OPERATOR'}])
                self.reply(200, 'application/json', json.dumps(receipt).encode())

        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = ApiClient(f'http://127.0.0.1:{server.server_port}')
                client.access_token = 'fictional-access'
                client.refresh_token = 'fictional-refresh'
                output = io.BytesIO()
                client.export_account(output)
                with ZipFile(output) as downloaded:
                    self.assertEqual(json.loads(downloaded.read('account.json')), {'fictional': True})
                with self.assertRaises(ClientError):
                    client.delete_account(token)
                self.assertIsNone(client.access_token)
                self.assertIsNone(client.refresh_token)
                progress = receipt_text(client.deletion_receipt(token))
                self.assertIn('删除尚未全部完成', progress)
                self.assertIn('备份：未核验', progress)
                self.assertIn('供应商 fictional：未核验', progress)
                self.assertEqual(calls, [('/v1/me/export', 'Bearer fictional-access', None),
                    ('/v1/me/deletion', 'Bearer fictional-access', {'confirmation': 'DELETE_MY_ACCOUNT', 'receipt_token': token}),
                    ('/v1/account-deletions/lookup', None, {'receipt_token': token})])
            finally:
                server.shutdown()
                thread.join()
