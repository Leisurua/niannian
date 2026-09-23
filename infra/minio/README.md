# MinIO development storage

Compose creates `nianian-private` idempotently and explicitly disables anonymous bucket access. The services bind only to localhost. Run `pwsh -File infra/smoke.ps1` from the repository root to check service health, pgvector, bucket creation, and anonymous access denial.

The bucket has no fixed expiration policy: the data-retention durations are still an open privacy decision (DB §20, D-011). The future FileAsset cleanup flow must delete objects according to authorized `retention_until` and revoke/delete state. No upload or signed URL implementation is part of this infrastructure task.
