import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from niannian_desktop.api import ApiClient, ApiError, ClientError, NetworkError
from niannian_desktop.lifecycle import DesktopLifecycle
from niannian_desktop.tasks import BackgroundTasks


def signed_in():
    client = ApiClient('http://localhost:8000')
    client.access_token, client.refresh_token = 'access', 'refresh'
    client.binding = {'id': 'binding', 'family_id': 'family'}
    return client


def test_refresh_retries_once_with_same_body_and_idempotency_key():
    client = signed_in()
    client._exchange = Mock(side_effect=[ApiError(401, 'AUTH_TOKEN_EXPIRED', 'expired'),
        {'access_token': 'new-access', 'refresh_token': 'new-refresh'}, {'id': 'message'}])
    assert client.send_text('hello', 'ELDER', 'NORMAL')['id'] == 'message'
    calls = client._exchange.call_args_list
    assert calls[0] == calls[2]
    assert calls[1].args == ('POST', '/v1/auth/refresh')
    assert client.refresh_token == 'new-refresh' and client.binding['id'] == 'binding'


def test_unconfirmed_refresh_is_not_replayed_and_logout_clears_local_secrets():
    client = signed_in()
    client._exchange = Mock(side_effect=[ApiError(401, 'AUTH_TOKEN_EXPIRED', 'expired'), NetworkError('offline')])
    with pytest.raises(ClientError, match='续期'):
        client._request('GET', '/v1/me')
    assert client.access_token is None and client.refresh_token is None and client.binding is None
    client = signed_in()
    client._exchange = Mock(side_effect=NetworkError('offline'))
    with pytest.raises(NetworkError):
        client.logout()
    assert client.access_token is None and client.refresh_token is None and client.binding is None


def test_unconfirmed_send_keeps_key_until_same_message_succeeds():
    client = signed_in()
    client._exchange = Mock(side_effect=[NetworkError('offline'), {'id': 'saved'}])
    with pytest.raises(NetworkError):
        client.send_text('hello', 'ELDER', 'NORMAL')
    with pytest.raises(ClientError, match='原内容'):
        client.send_text('different', 'ELDER', 'NORMAL')
    assert client.send_text('hello', 'ELDER', 'NORMAL')['id'] == 'saved'
    assert client._exchange.call_args_list[0] == client._exchange.call_args_list[1]


def test_logout_of_already_revoked_session_finishes_locally():
    client = signed_in()
    client._exchange = Mock(side_effect=ApiError(401, 'AUTH_SESSION_REVOKED', 'revoked'))
    client.logout()
    assert client.access_token is None and client.binding is None


def test_task_invalidation_discards_late_callbacks():
    tasks = BackgroundTasks()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def work():
        started.set(); release.wait(2); finished.set()
        return 'private old message'
    tasks.submit('old', work, Mock())
    assert started.wait(2)
    tasks.invalidate(); release.set()
    assert finished.wait(2)
    assert list(tasks.drain()) == []


def test_close_waits_for_running_login_then_revokes_it_and_destroys_window():
    class Window(DesktopLifecycle):
        pass
    app = Window()
    app.protocol = Mock(); app.after_cancel = Mock(); app.destroy = Mock()
    app._clear_message_view = Mock(); app._reset_session_view = Mock(); app._show_error = Mock()
    app.tasks = SimpleNamespace(invalidate=Mock(), submit=Mock())
    app._init_lifecycle()
    app.busy = True; app.polling = True; app._poll_after_id = 'poll'
    app.client = None
    app.close_window()
    app.after_cancel.assert_called_once_with('poll')
    app.tasks.submit.assert_not_called()
    client = Mock()
    assert app._discard_for_exit(True, (client, {}), '登录')
    app.busy = False; app._continue_exit()
    _, operation, finish = app.tasks.submit.call_args.args
    finish(operation())
    client.logout.assert_called_once()
    app.destroy.assert_called_once()
    assert app._closed and app.client is None
