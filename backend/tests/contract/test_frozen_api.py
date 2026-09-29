"""Static inventories for the frozen REST and conversation WebSocket contract."""

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _schema() -> dict:
    return yaml.safe_load((ROOT / "docs/openapi.yaml").read_text(encoding="utf-8"))


def _fixture(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_rest_operation_inventory() -> None:
    schema = _schema()
    assert schema["openapi"].startswith("3.")
    assert schema["servers"][0]["url"] == "/v1"

    expected = _fixture("operations.json")
    actual = [
        {"method": method.upper(), "path": path, "operation_id": operation["operationId"]}
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if method.lower() in HTTP_METHODS
    ]
    assert len(expected) == len(actual) == 74
    assert len({(entry["method"], entry["path"]) for entry in actual}) == 74
    assert len({entry["operation_id"] for entry in actual}) == 74
    assert actual == expected


def test_websocket_message_inventory_and_envelope() -> None:
    schema = _schema()
    expected = _fixture("websocket_messages.json")
    channels = schema["x-websocket-channels"]
    assert list(channels) == [expected["path"]]
    channel = channels[expected["path"]]
    assert channel["clientMessages"]["$ref"] == "#/components/schemas/WebSocketClientMessage"
    assert channel["serverMessages"]["$ref"] == "#/components/schemas/WebSocketServerMessage"

    schemas = schema["components"]["schemas"]
    envelope = schemas["WebSocketEnvelope"]
    assert envelope["required"] == expected["envelope_required"]
    assert set(envelope["properties"]) == set(expected["envelope_required"])
    assert envelope["properties"]["sequence"]["minimum"] == 1

    for direction, schema_name, count in (
        ("client_messages", "WebSocketClientMessage", 9),
        ("server_messages", "WebSocketServerMessage", 11),
    ):
        message = schemas[schema_name]
        assert message["allOf"][0]["$ref"] == "#/components/schemas/WebSocketEnvelope"
        actual = message["allOf"][1]["properties"]["type"]["enum"]
        assert len(actual) == len(set(actual)) == count
        assert actual == expected[direction]
