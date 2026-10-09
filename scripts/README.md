# E0-T08 fictional seed

Run from the repository root with the backend Python environment:

```powershell
backend/.venv/Scripts/python.exe scripts/seed_demo_data.py --check
backend/.venv/Scripts/python.exe -m pytest tests/demo -q -p no:cacheprovider
```

`--check` validates 28 fixed UUIDv7 rows in `DEMO_DATA:E0-T08` without connecting to PostgreSQL. The fixture includes fictional elder/child/family, active membership, granted/revoked Consent, confirmed/pending/revoked/deleted Memory, reminder feedback, signals, Mock notifications and attempts, structured report metrics, READY/FAILED reports, a simulated degraded device, and deletion pending cleanup metadata.

`demo_seed.SCENARIOS` describes simulated device/provider/deletion failures for fixture consumers. It is local fixture metadata, not an API payload or database field. The deleted Memory and `DELETE_REQUESTED` FileAsset represent the invisible-first, cleanup-pending state. No media object, cleanup job, provider request or hardware operation is performed by this seed. Business UI integration and real cleanup/provider/device acceptance require their own tasks and evidence.

Before using `--apply`, obtain the reviewed E0-T05 business migration and apply it through the migration task. This seed never creates tables. The current repository has no business revision; the live local PostgreSQL public schema is empty as checked on 2026-10-02.

For an existing demo schema, set these process environment variables explicitly:

```powershell
$env:APP_ENV = 'demo'
$env:DEMO_DATA = 'true'
$env:PROVIDER_MODE = 'mock'
# Set DATABASE_URL locally to the authorized demo database; keep credentials out of Git and logs.
backend/.venv/Scripts/python.exe scripts/seed_demo_data.py --apply
```

The CLI requires all three demo settings and `DATABASE_URL`; it does not automatically load `backend/config/demo.env`. It verifies required columns and the fixed rows' family/user/resource associations before any deletion. Replay deletes only fixed IDs in reverse dependency order, then inserts the fixture in one transaction. A namespace collision or missing schema aborts before writes; a write failure rolls back. Driver failures print only the exception type, with details redacted.

The in-memory replay tests verify fixed ID/content stability, unrelated row preservation and rollback behavior using a cursor double. They do not establish PostgreSQL constraints, cascade behavior or live replay idempotency. Database-generated defaults may change after delete/reinsert. Live first-write/repeated-replay acceptance is **NOT VERIFIED**, blocked by the missing schema. See [current evidence](../docs/evidence/E0-T08-completion-20261002.md).
