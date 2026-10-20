import pytest
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
