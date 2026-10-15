import asyncio
import threading

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app.ai.conversation import AIOrchestrator, CHAT, MockConversationLLM, UNKNOWN
from app.main import app
from backend.tests.integration.test_week3_postgres import URL, household, post, system, ws_frame

pytestmark = pytest.mark.skipif(not URL, reason='Set explicitly disposable WEEK3_TEST_DATABASE_URL')


def start(client, home):
    return post(client, '/v1/conversations', home[4], {'family_id': home[0], 'input_mode': 'TEXT'}).json()['id']


def handshake(ws, cid):
    assert ws.receive_json()['type'] == 'session.ready'
    ws.send_json(ws_frame(cid, 'session.start', 1, {'client_session_id': 'fictional', 'input_mode': 'TEXT'}))
    assert ws.receive_json()['type'] == 'session.ready'
    assert '我是念念 AI' in ws.receive_json()['payload']['text']


def test_mock_unknown_repeat_slow_down_end_and_no_transcript(system):
    client, engine, _, _ = system
    home = household(client)
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': '我女儿叫什么'}))
        assert ws.receive_json()['payload']['state'] == 'THINKING'
        answer = ws.receive_json()
        assert answer['payload'] == {'text': UNKNOWN, 'source_labels': ['Mock']}
        assert ws.receive_json()['payload']['state'] == 'IDLE'
        for seq, kind in ((3, 'repeat'), (4, 'slow_down')):
            ws.send_json(ws_frame(cid, kind, seq))
            assert ws.receive_json()['payload']['text'] == UNKNOWN
            assert ws.receive_json()['payload']['state'] == 'IDLE'
        ws.send_json(ws_frame(cid, 'session.end', 5, {'reason': 'USER'}))
        assert ws.receive_json()['payload']['state'] == 'IDLE'
    with engine.connect() as conn:
        record = conn.execute(text('SELECT provider_metadata,summary_text FROM conversation')).one()
        assert record[1] is None
        assert '我女儿' not in str(record)
        assert record[0]['trace']['provider'] == 'mock'


class HeldLLM(MockConversationLLM):
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()

    async def generate(self, request):
        self.started.set()
        try:
            while not self.release.is_set():
                await asyncio.sleep(0.01)
            return await super().generate(request)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


@pytest.mark.parametrize('stop', ['interrupt', 'session.end', 'disconnect', 'logout'])
def test_pending_turn_cannot_publish_after_interrupt_end_disconnect_or_revoke(system, stop):
    client, _, _, _ = system
    home = household(client)
    cid = start(client, home)
    llm = HeldLLM()
    app.state.conversation_orchestrator = AIOrchestrator(llm=llm)
    try:
        with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
            handshake(ws, cid)
            ws.send_json(ws_frame(cid, 'text.input', 2, {'text': '你好'}))
            assert ws.receive_json()['payload']['state'] == 'THINKING'
            assert llm.started.wait(2)
            if stop == 'logout':
                assert post(client, '/v1/auth/logout', home[4]).status_code == 204
                llm.release.set()
                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()
            elif stop == 'disconnect':
                ws.close()
            else:
                ws.send_json(ws_frame(cid, stop, 3))
                assert ws.receive_json()['type'] == 'assistant.state'
                assert llm.cancelled.wait(2)
                if stop == 'interrupt':
                    ws.send_json(ws_frame(cid, 'ping', 4))
                    assert ws.receive_json()['type'] == 'pong'
        if stop != 'logout':
            assert llm.cancelled.wait(2)
    finally:
        del app.state.conversation_orchestrator


def test_reconnect_does_not_repeat_identity_or_previous_reply(system):
    client, _, _, _ = system
    home = household(client)
    cid = start(client, home)
    path = '/v1/ws/conversations/' + cid
    with client.websocket_connect(path, headers=home[4]) as ws:
        handshake(ws, cid)
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': '你好'}))
        ws.receive_json()
        assert ws.receive_json()['payload']['text'] == CHAT
        ws.receive_json()
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'session.start', 3, {'client_session_id': 'fictional', 'input_mode': 'TEXT'}))
        assert ws.receive_json()['type'] == 'session.ready'
        ws.send_json(ws_frame(cid, 'repeat', 4))
        assert ws.receive_json()['type'] == 'error'
