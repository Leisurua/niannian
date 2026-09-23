# NianNian Coding Agent Rules

These rules apply to every Coding Agent task in this repository. Keep the 12-week course project small, testable, and honest.

## Source of Truth

When sources conflict, use this order:

1. The current Task Prompt and its acceptance criteria define scope, but do not silently override a frozen contract.
2. `nian-nian-requirements-design.md` defines product requirements.
3. Accepted ADRs define architecture: ADR-001 through ADR-007 only. ADR-008 through ADR-014 are Proposed, not facts.
4. `docs/design-freeze-review.md` and `docs/system-design.md` define the frozen architecture and change policy.
5. The contract for the touched surface is authoritative: `docs/api-spec.md`/OpenAPI and permission matrix; `docs/database-design.md`/data dictionary; UI, AI, Device, Privacy/Security contracts and their test matrices.
6. `docs/open-decisions.md` supplies only the recorded recommended default for an unresolved decision; it does not authorize a contract change.
7. `docs/development-plan.md` and `docs/development-checklist.md` describe execution and verification, not new requirements.

If a conflict remains, stop the affected implementation and report it. Do not choose the most convenient interpretation.

## Repository Shape

- `backend/app/modules/`: `auth`, `family`, `consent`, `memory`, `conversation`, `reminder`, `safety`, `signal`, `notification`, `report`, `emergency`, `device`, and `audit` domains. Each module owns its API/service/repository/model/schemas; cross-module calls use public services, commands, or events.
- `backend/app/integrations/`: provider adapters and deterministic mocks. `backend/app/platform/`: settings, database, logging, storage, task/outbox. `backend/app/worker/`: scheduler, lease, retry, and dead-letter handling.
- `android/app-elder/` and `android/app-family/`: separate Kotlin + Jetpack Compose apps. `android/core-*` and `android/feature-*` are shared modules; `android/device/{ble,kiosk,camera,wakeword,telecom}` is Elder-only capability code.
- `infra/`: local PostgreSQL/pgvector and MinIO/Compose support. `tests/`: `unit`, `integration`, `contract`, `ai`, `security`, `device`, and `demo` suites.

## Non-Negotiable Task Rules

- Execute only the specified Task, once. Do not expand Scope, start `Next`, or perform another development task automatically.
- Do not change Requirements, OpenAPI/WSS, public enums/states, DB schema/constraints/migrations, Consent scope, family boundary, or Security Boundary without an approved Proposal/ADR and the required review.
- A Contract, enum, state-machine, or Security Boundary conflict stops the affected work and must be reported.
- Enforce family scope, Consent, ownership, role, and resource state in service/query layers. Never bypass Family or Consent permission because the UI hides a control.
- LLMs may propose language, candidates, or signals only. They never decide permission, facts, notifications, scam verdicts, emergency state, or other sensitive actions.
- `Memory=PENDING` is not a family fact and is never RAG context. RAG requires confirmed, authorized, same-family, not-deleted data.
- Raw Audio is not persisted by default. Any exception needs an approved privacy decision, minimization, automatic expiry, and tests.
- Never commit secrets, tokens, full phone numbers, real family data, raw audio, camera frames, or sensitive transcripts. Redact logs and fixtures.
- Mocks must be deterministic and visibly labelled (`provider=mock`, Demo/Mock status). Never present mock delivery, connection, or provider output as real.
- Do not opportunistically refactor unrelated modules or fix bugs outside the current Task.

## Engineering Constraints

### Backend

- Use the accepted Python/FastAPI/Pydantic/SQLAlchemy/Alembic modular-monolith design. Keep routes thin; enforce policy in services and repositories.
- Do not import another module's private repository/model. API and worker share domain code but are separate process boundaries.
- PostgreSQL is the system of record; pgvector stays within the same permission boundary. Use private S3-compatible storage with authorized, expiring Signed URLs.
- Background work uses the accepted APScheduler worker plus PostgreSQL task/outbox semantics: idempotency keys, leases, bounded retries, timeout, backoff, and observable dead-letter failure.
- Keep async DB access, type validation, migrations, redacted structured logging, and audit behavior consistent with existing contracts.

### Android

- Use Kotlin + Compose, ViewModel/StateFlow/Repository, and small UseCases where useful. `app-elder` owns hardware permissions; `app-family` does not carry them unnecessarily.
- Device adapters expose capability state/events only. They do not create business SignalEvents, send notifications, call the LLM, or decide Emergency policy.
- Keep tokens in Keystore-backed storage, sensitive local data scoped by family/owner/version/expiry, and pending actions idempotent. Show explicit offline, permission-denied, degraded, and mock states.

### AI

- Business code depends on adapter DTOs/capabilities, never vendor SDK types. Every provider call has timeout, bounded retry, fallback, redaction, schema validation, provider/version, and prompt-version evidence.
- Apply deterministic authorization, Consent, safety rules, and post-LLM validation before side effects. Unknown or conflicting facts stay unknown/candidate.

### Device and Security

- Treat kiosk, BLE, CameraX, wake word, audio ownership, telephony, OEM behavior, and exact permissions as observed capabilities with honest fallbacks until the named-device gate passes.
- Camera presence emits only presence state; discard frames and do not identify people or create biometric templates. One audio owner at a time; wake word is not identity authentication.
- Emergency is idempotent and reports only observed outcomes; launching an intent is not `CONNECTED`. Revoke/delete is invisible-first and propagates to cache, vector, file, export, and notification paths.
- Use deny-by-default authorization, minimal notification payloads, private buckets, short-lived URLs, append-only audit records, and stable redacted error/log fields.

## Tests and Verification

- Run the tests corresponding to every changed surface: unit for domain/policy, integration for DB/worker/storage, contract for OpenAPI/WSS/adapters, AI/security/device/demo tests when applicable.
- A test result is `PASS` only when it actually ran and passed. If it cannot run, write `NOT VERIFIED` and the concrete reason. Never call “code looks correct” a pass.
- Do not claim real provider, hardware, delivery, call connection, or performance acceptance without the required evidence.

## Design Change Policy

Ordinary implementation details (class names, helper placement, fixture IDs, conservative retry/backoff values, Compose internals, prompt wording that preserves the contract) may be chosen locally and tested.

Anything affecting an API/WSS field or operation, DB entity/constraint/enum/migration, Requirement, Consent/family boundary, cross-module contract, security boundary, data retention, identity/biometric behavior, or public state is a Proposal/ADR only. Stop and report; do not implement it as an incidental fix.

## Task Completion Format

Every completed Task must end with exactly these sections:

```text
## Task
## Changed
## Tests
## Decisions
## Contract Changes
## Not Verified
## Issues
## Next
```

`Contract Changes` is `None` in the normal case. `Next` records follow-up work only; it is never executed automatically.

