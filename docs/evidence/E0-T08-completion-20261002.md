# E0-T08 fixture implementation and acceptance — 2026-10-02

## Task

E0-T08 only: complete fictional demo fixtures and safe replay tooling. Fixture implementation is **PASS**; end-to-end database seed acceptance remains **BLOCKED**, so the full gate is not marked complete.

Basis: development-plan E0-T08 and §10; database-design §26.3; the frozen data dictionary; api-spec §18; UI Demo §15; D-015's recorded fictional/Mock default.

## Changed

- Extended 24 existing rows to 28 fixed UUIDv7 rows, keeping the `DEMO_DATA:E0-T08` namespace and old identifiers. Added a deleted Memory, cleanup-pending FileAsset metadata, a visibly Mock degraded DeviceBinding, and an authorized failed MISS_FAMILY signal.
- The file row is a zero-byte metadata placeholder only, not a persisted photo/audio/object. Local `SCENARIOS` explicitly labels simulated device, provider and deletion partial failures; it adds no API/DB field or job.
- Corrected the PHYSICAL_DISCOMFORT example to WITHHELD: HEALTH_MEDICATION is revoked. The failed notification now references an authorized MISS_FAMILY event instead. No protected signal receives a notification.
- Replay checks all supplied family/user/resource association markers, validates fixtures even under optimized Python, bounds connection startup to five seconds, and redacts driver failure details. Success output explicitly includes `provider=mock, fictional=true`.
- Added frozen dictionary checks and safety/rollback/repeat tests, usage documentation and current gate evidence. Existing unrelated working-tree changes are preserved.

## Tests

| Actual check | Result |
| --- | --- |
| `backend/.venv/Scripts/python.exe scripts/seed_demo_data.py --check` | PASS; 28 deterministic fictional rows, no DB access. [Output](E0-T08/2026-10-02/fixture-check.txt). |
| `backend/.venv/Scripts/python.exe -m pytest tests/demo -q -p no:cacheprovider --basetemp=.task-temp/e0-t08-completion` | PASS; 30 tests. Frozen columns/required fields/enums, fixture relationships, consent withholding, missing schema, 13 ownership collisions, repeat stability with unrelated rows, rollback and CLI error redaction. Replay uses a cursor double. |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests tests -q -p no:cacheprovider --basetemp=.task-temp/e0-t08-regression` | PASS; 84 tests, including Demo, API/WSS/adapters and existing security/artifact scans. Expected logging failure-path output appears; one dependency deprecation warning. |
| Final `backend/.venv/Scripts/python.exe -m pytest backend/tests tests -q -o addopts= -p no:cacheprovider --basetemp=.task-temp/e0-t08-final --junitxml=.task-temp/e0-t08-final-tests.xml` | PASS after the final code/documentation edits; 84 passed, one dependency warning. [Output](E0-T08/2026-10-02/regression.txt). |
| Final `backend/.venv/Scripts/python.exe -m unittest discover -s tests/security -p test_*.py -v` | PASS; 15 tests, no skips, including source/fixture/Git/available APK scans and existing logging privacy checks. [Output](E0-T08/2026-10-02/security-scan.txt). |
| Local Compose PostgreSQL read-only inventory | PASS as a connectivity/inventory check: public tables `[]`; pgvector `0.8.6`. Repository has no business migration versions directory. [Output](E0-T08/2026-10-02/database-preflight.txt). |
| Actual `--apply` with explicit demo/fictional/Mock settings against local PostgreSQL | Correctly rejected with exit 1 at schema validation, before DELETE/INSERT. This proves the missing-schema refusal path, **not** successful seeding. |
| `git -c safe.directory=D:/class_project diff --check` | PASS. |

## Decisions

Use only frozen states/fields and deterministic fictional fixture data. The deleted Memory remains deleted while cleanup is simulated as pending/failed. Device states are simulated capabilities, not named-device evidence. PENDING/REVOKED/DELETED fixtures are not asserted as RAG context. Runtime timestamps/defaults can regenerate on delete/reinsert and must be checked separately in live acceptance.

## Contract Changes

None. No requirements, API/WSS, enums, database schema/constraints/migrations, Consent scopes or security boundary were changed.

## Not Verified

First PostgreSQL persistence, repeated live replay, actual DB FK/check/default/cascade behavior, preservation of outside records in a real DB, UI seed rendering, actual cleanup retries, provider delivery, hardware capability or performance acceptance: **NOT VERIFIED**. The real DB has no business tables. Existing apps do not load business fixtures. The in-memory tests do not replace these gates.

## Issues

E0-T05 remains a plan without a reviewed business migration. This is the current blocker; Docker/PostgreSQL connectivity and psycopg are available now. Implementing that migration would start another Task and exceed E0-T08. The fixture implementation can be reviewed now; successful DB replay acceptance cannot be closed honestly.

## Next

After the reviewed business schema is available, rerun this task's live acceptance: record migration/table inventory, apply seed, read back all 28 fixed IDs and supplied fields/states/references, repeat apply, compare stable IDs/counts/fixture fields and inspect preserved outside records and regenerated defaults. UI vertical-slice acceptance belongs to E11-T01. These follow-ups were not executed.
