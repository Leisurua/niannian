import importlib
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest

from niannian_desktop.api import ApiClient, NetworkError
from niannian_desktop.settings import load_base_url, save_base_url


@pytest.fixture(params=["family", "elder"])
def client_modules(request):
    if request.param == "family":
        package, client_name, app_name = (
            "niannian_family_client", "NianNianClient", "FamilyClientApp"
        )
    else:
        package, client_name, app_name = (
            "niannian_elder_demo", "ElderClient", "ElderDemoApp"
        )
    api = importlib.import_module(package + ".api")
    ui = importlib.import_module(package + ".app")
    return api, ui, client_name, app_name


@pytest.mark.parametrize("box", ["INBOX", "OUTBOX"])
def test_message_listing_follows_server_cursor(box):
    client = ApiClient("http://localhost:8000")
    client._request = Mock(side_effect=[
        {"items": [{"id": str(i), "sequence": 9000 + i} for i in range(100)],
         "page": {"has_more": True, "next_cursor": "250"}},
        {"items": [{"id": "newest"}], "page": {"has_more": False, "next_cursor": None}},
    ])
    items = client.list_messages(box)
    assert len(items) == 101
    assert items[-1]["id"] == "newest"
    queries = [parse_qs(urlparse(call.args[1]).query) for call in client._request.call_args_list]
    assert [query["after_sequence"] for query in queries] == [["0"], ["250"]]
    assert all(query["box"] == [box] and query["limit"] == ["100"] for query in queries)


@pytest.mark.parametrize("cursor", [None, "", "invalid", "0", "-1"])
def test_message_listing_rejects_invalid_cursor(cursor):
    client = ApiClient("http://localhost:8000")
    client._request = Mock(return_value={
        "items": [], "page": {"has_more": True, "next_cursor": cursor},
    })
    with pytest.raises(NetworkError):
        client.list_messages("INBOX")
    assert client._request.call_count == 1


def test_message_listing_rejects_repeated_cursor():
    client = ApiClient("http://localhost:8000")
    client._request = Mock(return_value={
        "items": [], "page": {"has_more": True, "next_cursor": "100"},
    })
    with pytest.raises(NetworkError):
        client.list_messages("INBOX")
    assert client._request.call_count == 2


def test_polling_toggle_keeps_one_timer(client_modules):
    _, ui, _, app_name = client_modules
    app_type = getattr(ui, app_name)
    enabled = Mock(return_value=True)
    app = SimpleNamespace(
        polling=False, busy=False, _poll_after_id=None,
        auto_poll_var=SimpleNamespace(get=enabled), auto_var=SimpleNamespace(get=enabled),
        client=SimpleNamespace(binding={"id": "fictional-device"}),
        after=Mock(side_effect=["timer-1", "timer-2"]), after_cancel=Mock(),
        refresh_messages=Mock(),
    )
    app._poll_tick = lambda: app_type._poll_tick(app)
    app_type._toggle_polling(app)
    enabled.return_value = False
    app_type._toggle_polling(app)
    enabled.return_value = True
    app_type._toggle_polling(app)
    app.after_cancel.assert_called_once_with("timer-1")
    assert app._poll_after_id == "timer-2"
    assert app.refresh_messages.call_count == 2


def test_busy_polling_reschedules_without_starting_work(client_modules):
    _, ui, _, app_name = client_modules
    app_type = getattr(ui, app_name)
    app = SimpleNamespace(
        polling=True, busy=True, _poll_after_id=None,
        after=Mock(return_value="timer-1"), refresh_messages=Mock(),
    )
    app._poll_tick = lambda: app_type._poll_tick(app)
    app._poll_tick()
    app.refresh_messages.assert_not_called()
    app.after.assert_called_once_with(3000, app._poll_tick)
    assert app._poll_after_id == "timer-1"


@pytest.mark.parametrize("method", ["login", "test_connection"])
def test_network_task_captures_url_before_worker(client_modules, monkeypatch, method):
    _, ui, client_name, app_name = client_modules
    app_type = getattr(ui, app_name)
    client_factory = Mock()
    client_factory.return_value.health.return_value = {"status": "ok"}
    monkeypatch.setattr(ui, client_name, client_factory)
    url = Mock(return_value="http://localhost:8000")
    app = SimpleNamespace(url_var=SimpleNamespace(get=url))
    app._client_for_url = lambda: client_factory(app.url_var.get())

    def run(_label, operation, _success):
        url.side_effect = AssertionError("Tk variable read by background task")
        operation()

    app._run = run
    getattr(app_type, method)(app)
    client_factory.assert_called_once_with("http://localhost:8000")


def test_family_send_captures_priority_before_worker(monkeypatch):
    ui = importlib.import_module("niannian_family_client.app")
    priority = Mock(return_value="IMPORTANT")
    client = Mock(binding={"id": "fictional-device"})
    app = SimpleNamespace(
        _require_client=lambda: client,
        message_var=SimpleNamespace(get=lambda: "  fictional message  "),
        priority_var=SimpleNamespace(get=priority),
    )

    def run(_label, operation, _success):
        priority.side_effect = AssertionError("Tk variable read by background task")
        operation()

    app._run = run
    ui.FamilyClientApp.send_message(app)
    client.send_text_to_role.assert_called_once_with("fictional message", "ELDER", "IMPORTANT")


def test_settings_ignore_bad_files_and_store_only_server_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    for application in ("NianNianFamily", "NianNianElderDemo"):
        assert load_base_url(application) is None
        save_base_url(application, "localhost:8000/v1/")
        path = tmp_path / application / "settings.json"
        assert json.loads(path.read_text(encoding="utf-8")) == {"base_url": "http://localhost:8000"}
        assert load_base_url(application) == "http://localhost:8000"
        for content in ("not json", "[]", "null", '{"base_url":"ftp://localhost"}'):
            path.write_text(content, encoding="utf-8")
            assert load_base_url(application) is None


def test_server_address_rejects_credentials_and_invalid_ports():
    for address in (
        "http://fictional-user@localhost:8000", "http://localhost:0",
        "http://localhost:65536", "http://localhost:invalid",
        "http://localhost:8000?token=fictional", "http://localhost:8000#fragment",
    ):
        with pytest.raises(ValueError):
            ApiClient(address)
