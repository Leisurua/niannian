import pytest
from sqlalchemy import text

from app.ai.conversation import AIOrchestrator
from app.main import app
from app.modules.safety.rules import WARNING
from backend.tests.integration.test_week3_postgres import URL, system, household, ws_frame
from backend.tests.integration.test_week4_postgres import handshake, start

pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable WEEK3_TEST_DATABASE_URL required')


class Unavailable:
    def capabilities(self):
        raise AssertionError('Safety must run before a provider is consulted')


@pytest.mark.parametrize('outage', [False, True])
def test_warning_arrives_before_reply_without_summary_or_notification_grant(system, outage):
    client, engine, _, _ = system
    home = household(client)
    cid = start(client, home)
    utterance = '有人让我把验证码告诉他，还说别告诉孩子。'
    if outage:
        app.state.conversation_orchestrator = AIOrchestrator(
            llm=Unavailable(), tts=Unavailable(), avatar=Unavailable())
    try:
        with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
            handshake(ws, cid)
            ws.send_json(ws_frame(cid, 'text.input', 2, {'text': utterance}))
            thinking, warning, reply, state = [ws.receive_json() for _ in range(4)]
            assert thinking['payload']['state'] == 'THINKING'
            assert warning['type'] == 'warning'
            assert warning['payload'] == {
                'reason_category': 'VERIFICATION_CODE_AND_SECRECY', 'display_text': WARNING}
            assert reply['payload'] == {'text': WARNING, 'source_labels': ['Mock']}
            assert state['payload']['state'] == 'WARNING'
            assert [f['sequence'] for f in (thinking, warning, reply, state)] == list(
                range(thinking['sequence'], thinking['sequence'] + 4))
            ws.send_json(ws_frame(cid, 'ping', 3))
            assert ws.receive_json()['type'] == 'pong'
        with engine.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM consent')).scalar() == 0
            assert conn.execute(text('SELECT summary_text FROM conversation')).scalar() is None
            assert utterance not in str(conn.execute(text('SELECT provider_metadata FROM conversation')).scalar())
    finally:
        if outage:
            del app.state.conversation_orchestrator
