import pytest
import json
import httpx
import asyncio
import threading
from app.ai.conversation import AIOrchestrator
from app.integrations.openai_compatible import OpenAICompatibleLLM
from app.modules.conversation import api
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from backend.tests.support import URL, household, post, ws_frame

pytestmark = pytest.mark.skipif(not URL, reason='Set TEST_DATABASE_URL to run PostgreSQL integration tests')

def test_wss_owner_identity_reconnect_replay_and_end(system):
    client, engine, _, _ = system
    home = household(client)
    cid = post(client, '/v1/conversations', home[4], {'family_id': home[0], 'input_mode':'TEXT'}).json()['id']
    path = '/v1/ws/conversations/' + cid
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers=home[2]): pass
    with client.websocket_connect(path, headers=home[4]) as ws:
        ready = ws.receive_json(); assert ready['type'] == 'session.ready'
        ws.send_json(ws_frame(cid, 'session.start', 1, {'client_session_id':'fictional-client', 'input_mode':'TEXT'}))
        assert ws.receive_json()['type'] == 'session.ready'
        identity = ws.receive_json(); assert 'Mock' in identity['payload']['text']
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text':'虚构输入不应持久化'}))
        assert ws.receive_json()['payload']['state'] == 'THINKING'
        assert ws.receive_json()['type'] == 'assistant.text'
        last = ws.receive_json()['sequence']
    with client.websocket_connect(path, headers=home[4]) as ws:
        assert ws.receive_json()['sequence'] > last
        ws.send_json(ws_frame(cid, 'session.start', 3, {'client_session_id':'fictional-client', 'input_mode':'TEXT'}))
        assert ws.receive_json()['type'] == 'session.ready'
        ws.send_json(ws_frame(cid, 'ping', 4))
        assert ws.receive_json()['type'] == 'pong'
        ws.send_json(ws_frame(cid, 'ping', 4))
        assert ws.receive_json()['payload']['code'] == 'WS_SEQUENCE_REPLAY'
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'session.end', 5, {'reason':'USER'}))
        assert ws.receive_json()['payload']['state'] == 'IDLE'
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers=home[4]): pass
    assert client.get('/v1/conversations/'+cid, headers=home[4]).json()['status'] == 'COMPLETED'
    with engine.connect() as conn:
        assert '虚构输入不应持久化' not in str(conn.execute(text('SELECT provider_metadata,summary_text FROM conversation')).all())


def test_wss_revoked_login_closes_live_connection_and_audio_is_disabled(system):
    client, _, _, _ = system
    home = household(client)
    assert post(client, '/v1/conversations', home[4], {'family_id':home[0], 'input_mode':'VOICE'}).status_code == 503
    cid = post(client, '/v1/conversations', home[4], {'family_id':home[0], 'input_mode':'TEXT'}).json()['id']
    path = '/v1/ws/conversations/'+cid
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        assert post(client, '/v1/auth/logout', home[4]).status_code == 204
        ws.send_json(ws_frame(cid,'ping',1))
        with pytest.raises(WebSocketDisconnect): ws.receive_json()


def test_wss_malformed_audio_family_loss_and_parallel_connections(system):
    client, _, _, _ = system
    home = household(client)
    assert post(client, '/v1/conversations', home[2], {'family_id':home[0], 'input_mode':'TEXT'}).status_code == 403
    cid = post(client, '/v1/conversations', home[4], {'family_id':home[0], 'input_mode':'TEXT'}).json()['id']
    path = '/v1/ws/conversations/'+cid
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path, headers=home[4]): pass
        ws.send_text('{invalid')
        assert ws.receive_json()['payload']['code'] == 'WS_INVALID_MESSAGE'
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'audio.chunk', 1, {'base64_data':'fictional'}))
        assert ws.receive_json()['payload']['code'] == 'WS_AUDIO_DISABLED'
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        members = client.get('/v1/families/'+home[0]+'/members', headers=home[2]).json()['items']
        elder = next(m for m in members if m['user_id'] == home[3])
        result = client.patch('/v1/families/'+home[0]+'/members/'+elder['id'],
            headers={**home[2], 'If-Match':str(elder['version'])}, json={'status':'REVOKED'})
        assert result.status_code == 200
        ws.send_json(ws_frame(cid, 'ping', 1))
        with pytest.raises(WebSocketDisconnect): ws.receive_json()


def test_real_adapter_two_turns_failure_recovery_reconnect_and_no_transcript(system, monkeypatch):
    client, engine, _, _ = system
    home = household(client)
    requests = []
    def provider(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        requests.append(payload)
        if payload['user_input'] == '模拟供应商失败':
            return httpx.Response(429, text='private upstream error')
        reply = '您刚才说喜欢月季。' if payload['recent_turns'] else '我们聊聊您喜欢的花吧。'
        output = dict(reply=reply, memory_refs=[], intent='GENERAL_CHAT', needs_clarification=False,
                      memory_candidates=[], signal_candidates=[], blocked_action=None, uncertainty_reason=None)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(output)}}]})
    llm = OpenAICompatibleLLM(base_url='https://llm.example/v1', api_key='fictional-key',
        model='fictional-model', transport=httpx.MockTransport(provider))
    monkeypatch.setattr(api, 'configured_orchestrator', lambda settings: AIOrchestrator(llm=llm))
    cid = post(client, '/v1/conversations', home[4], {'family_id': home[0], 'input_mode': 'TEXT'}).json()['id']
    path = '/v1/ws/conversations/' + cid
    with client.websocket_connect(path, headers=home[4]) as ws:
        assert ws.receive_json()['payload']['llm_mode'] == 'real'
        ws.send_json(ws_frame(cid, 'session.start', 1, {'client_session_id': 'fictional', 'input_mode': 'TEXT'}))
        ws.receive_json()
        identity = ws.receive_json()['payload']
        assert identity['source_labels'] == ['AI'] and 'Mock' not in identity['text']
        for seq, value in ((2, '我喜欢月季'), (3, '我刚才喜欢什么花'), (4, '模拟供应商失败'), (5, '继续聊聊')):
            ws.send_json(ws_frame(cid, 'text.input', seq, {'text': value}))
            assert ws.receive_json()['payload']['state'] == 'THINKING'
            answer = ws.receive_json()['payload']
            assert answer['source_labels'] == ['AI']
            if seq == 3:
                assert answer['text'] == '您刚才说喜欢月季。'
            if seq == 4:
                assert ws.receive_json()['type'] == 'error'
                assert ws.receive_json()['payload']['state'] == 'ERROR'
            else:
                assert ws.receive_json()['payload']['state'] == 'IDLE'
    assert requests[0]['recent_turns'] == []
    assert requests[1]['recent_turns'][0]['user'] == '我喜欢月季'
    assert all(t['user'] != '模拟供应商失败' for t in requests[3]['recent_turns'])
    with client.websocket_connect(path, headers=home[4]) as ws:
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'session.start', 6, {'client_session_id': 'again', 'input_mode': 'TEXT'}))
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'text.input', 7, {'text': '重新开始'}))
        ws.receive_json()
        assert ws.receive_json()['payload']['text'] == '我们聊聊您喜欢的花吧。'
        ws.receive_json()
    assert requests[-1]['recent_turns'] == []
    with engine.connect() as conn:
        stored = str(conn.execute(text('SELECT provider_metadata,summary_text FROM conversation')).all())
        assert '我喜欢月季' not in stored
        assert 'private upstream error' not in stored
        assert 'openai_compatible' in stored


def test_real_reply_and_history_are_discarded_when_memory_is_revoked_in_flight(system, monkeypatch):
    from backend.tests.integration.test_rag_offline import FACT, setup_memory
    from app.ai.conversation import UNKNOWN
    client, _, _, _ = system
    home, _, consent = setup_memory(system)
    entered, release = threading.Event(), threading.Event()
    requests = []
    async def provider(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        requests.append(payload)
        if len(requests) == 1:
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        output = dict(reply=FACT, memory_refs=[], intent='GENERAL_CHAT', needs_clarification=False,
                      memory_candidates=[], signal_candidates=[], blocked_action=None, uncertainty_reason=None)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(output)}}]})
    llm = OpenAICompatibleLLM(base_url='https://llm.example/v1', api_key='fictional-key',
        model='fixture', transport=httpx.MockTransport(provider))
    monkeypatch.setattr(api, 'configured_orchestrator', lambda settings: AIOrchestrator(llm=llm))
    cid = post(client, '/v1/conversations', home[4], {'family_id': home[0], 'input_mode': 'TEXT'}).json()['id']
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'session.start', 1, {'client_session_id': 'fictional', 'input_mode': 'TEXT'}))
        ws.receive_json(); ws.receive_json()
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': FACT}))
        ws.receive_json()
        assert entered.wait(2)
        assert requests[0]['authorized_memory']
        assert post(client, '/v1/consents/' + consent + '/revoke', home[4]).status_code == 201
        release.set()
        assert ws.receive_json()['payload']['text'] == UNKNOWN
        ws.receive_json()
        ws.send_json(ws_frame(cid, 'text.input', 3, {'text': '我们换个话题'}))
        ws.receive_json(); ws.receive_json(); ws.receive_json()
    assert requests[1]['authorized_memory'] == []
    assert requests[1]['recent_turns'] == []
