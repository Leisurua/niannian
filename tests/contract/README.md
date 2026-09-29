E0-T06 static fixtures live in backend/tests/contract/. operations.json records the 74 REST method/path/operationId tuples. websocket_messages.json records the conversation channel, shared envelope, and 9 client / 11 server message types from docs/openapi.yaml and docs/api-spec.md section 20.

Run python -m pytest backend/tests/contract backend/tests/test_openapi_source.py -q -p no:cacheprovider from the repository root. Review any mismatch against the frozen contract before changing a fixture. audio.chunk is in the current inventory; its use remains conditional on the final audio policy.
