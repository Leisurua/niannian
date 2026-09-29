# E0-T05 Alembic initial schema task plan

Status: plan only. This document does not create or apply a migration.

## Basis and dependency

- Scope and acceptance: `docs/development-plan.md` E0-T05. The only dependency is E0-T04.
- E0-T04 has a recorded `PASS` in `docs/development-checklist.md` for Compose health, pgvector, private MinIO bucket, and denied anonymous listing. Recheck infrastructure availability before executing a future migration; a prior smoke result is not a live service guarantee.
- Entity inventory and migration policy: `docs/database-design.md` §§4, 26. At implementation time, use `docs/data-dictionary.md` for exact fields, types, nullability, foreign keys, checks, and indexes. Do not infer a new schema from this ordering plan.
- Accepted architecture: ADR-003 and ADR-006. PostgreSQL and pgvector share the permission boundary; binary objects remain in private S3-compatible storage.

## Initial revision ordering

Use one reviewed initial schema revision or a short linear sequence in the order below. A numbered row means its table can be created after the preceding dependencies exist. Self-references may be declared when creating their own table. Keep the revision identifiers in `YYYYMMDD_<short_slug>` form and record every `down_revision`. Do not put demo seed data into schema revisions.

| Order | Entity / table | Must already exist before its foreign keys |
| ---: | --- | --- |
| 1 | User / `user` | — |
| 2 | Family / `family` | `user` |
| 3 | AuditLog / `audit_log` | `user`, `family` |
| 4 | FamilyMember / `family_member` | `user`, `family` |
| 5 | FamilyInvitation / `family_invitation` | `user`, `family` |
| 6 | Consent / `consent` | `user`, `family`, `audit_log`; `consent.replaced_by_id` is a self-reference |
| 7 | DeviceBinding / `device_binding` | `user` |
| 8 | DeviceSession / `device_session` | `user`, `device_binding` |
| 9 | Memory / `memory` | `user`, `family` |
| 10 | MemoryChunk / `memory_chunk` | `memory` |
| 11 | MemoryEmbedding / `memory_embedding` | `memory_chunk`; pgvector extension must be available |
| 12 | Reminder / `reminder` | `user` |
| 13 | ReminderExecution / `reminder_execution` | `reminder`, `user` |
| 14 | Conversation / `conversation` | `user`, `family`, `device_binding` |
| 15 | ConversationMessage / `conversation_message` | `conversation` |
| 16 | FileAsset / `file_asset` | `user`, `family`, `memory`, `conversation` |
| 17 | InteractionMetric / `interaction_metric` | `user` |
| 18 | SignalEvent / `signal_event` | `user`, `family`, `conversation`, `conversation_message`; `signal_event.duplicate_of_id` is a self-reference |
| 19 | Notification / `notification` | `signal_event`, `reminder_execution`, `user` |
| 20 | NotificationAttempt / `notification_attempt` | `notification` |
| 21 | EmergencyContact / `emergency_contact` | `user` |
| 22 | WeeklyReport / `weekly_report` | `user`, `family`; `weekly_report.supersedes_id` is a self-reference |

This is a topological order, not an authorization to split related constraints across unreviewed revisions. Create indexes and checks with their owning table or in a subsequent reviewed revision before application use. Use the data dictionary's actual FK delete actions; an optional relationship is not grounds to remove its FK. Confirm the extension precondition before creating `memory_embedding`. Initial small-data vector search uses the documented hard filters and exact cosine query; an ANN index needs separate evidence and review.

## Schema plan review checklist

- [ ] Compare the revision's table inventory against all 22 rows above and DB §4; no extra `RiskRule` table or missing normalization table.
- [ ] Compare every column, type, default, nullability, UUID key, FK target/delete action, self-reference, and CHECK with `docs/data-dictionary.md`; keep public statuses and scopes unchanged. Resolve a contract discrepancy before coding it.
- [ ] Review unique and partial indexes, especially active/pending `family_member`, invitation/token and device hashes, reminder occurrence, Consent grant lookup, and notification dedupe. Review lock duration and online index strategy if needed.
- [ ] Review PII and retention: encrypted/hashed phone fields, hashed refresh and invitation tokens, no raw audio or public object URL, `retention_until` where specified, and redacted audit metadata. Do not invent a retention duration while the privacy decision is open.
- [ ] Review family/Consent boundaries: schema supports required family and subject keys; service-layer transactional checks remain required for cross-family relationships and authorization. A FK alone does not prove authorization.
- [ ] Review migration role and connection: DDL uses the migrator, runtime uses least privilege, and secrets stay outside the revision and logs.
- [ ] Record reviewer approval for schema, PII, indexes, and rollback before applying to demo/staging. A proposed contract change follows the repository Proposal/ADR policy first.

## Required verification and rollback evidence for a future revision

For each actual revision, attach the revision ID and commit, reviewer, environment, UTC time, commands, exit codes, redacted output, and evidence paths. Use a disposable database before any shared environment.

1. **Preflight:** capture E0-T04 smoke result, pgvector availability/version, a backup and restore procedure, Alembic `current`/`heads`, and the expected empty or known starting schema. Do not expose credentials in evidence.
2. **Apply:** run upgrade on a disposable database. Save `alembic current`, an inventory query proving exactly the intended 22 business tables, FK/check/index inspection, and targeted integrity tests. Diff the resulting schema against the data dictionary; `autogenerate` output is a review aid, not approval.
3. **Empty-schema downgrade rehearsal:** only before inserting data, run the proposed downgrade on a fresh disposable database, then show the preceding revision, table inventory, and a successful re-upgrade. Save commands and results. Do not run a destructive downgrade on a populated database.
4. **Populated-schema recovery rehearsal:** insert only fictional test data, take a backup, exercise a restore into a separate disposable database, and verify row counts and representative constraints there. For a released or populated revision, document a forward-fix revision and its verification query as the operational rollback path; do not claim that deleting columns or restoring an old backup is a safe automatic rollback.
5. **Promotion:** record the same apply and verification queries for demo/staging, then seek production approval under DB §26. If a step fails, stop promotion, preserve the failure output, and use the documented forward-fix or isolated restore procedure.

E0-T05 schema plan review is satisfied by checking this document against DB §§4/26 and the data dictionary. Actual apply, downgrade, restore, and production evidence belong to the later migration implementation task; they are not claimed here.
