# MinIO development storage

Compose creates `nianian-private` idempotently and explicitly disables anonymous bucket access. The services bind only to localhost. Run `pwsh -File infra/smoke.ps1` from the repository root to check service health, pgvector, bucket creation, and anonymous access denial.

The bucket has no fixed expiration policy: the data-retention durations are still an open privacy decision (DB §20, D-011). The future FileAsset cleanup flow must delete objects according to authorized `retention_until` and revoke/delete state. No upload or signed URL implementation is part of this infrastructure task.
# Reproducible local MinIO images

The original MinIO and mc release image repositories returned anonymous pull
errors in the 2026-09-29 GitHub run. Their archived binary download endpoints
also returned HTTP 410. `Dockerfile` now builds the **same upstream versions**:

- Server `RELEASE.2025-02-18T16-25-55Z`, commit `90f5e1e5f62cbc47be6d0a3ca0634bfd84c2248c`.
- Client `RELEASE.2025-02-08T19-14-21Z`, commit `bd925c01a1ccab367993f20c251b7bae9d22f8a5`.

Sources come from the upstream `minio/minio` and `minio/mc` GitHub repositories.
Git commits, Go 1.23.6 and Alpine base-image digests are fixed. The build verifies
the fetched commit and uses the upstream module checksums with `-mod=readonly`.
Go/git stay in build stages; runtime images contain the binary, CA certificates,
curl for the existing health check and the upstream AGPL-3.0-or-later LICENSE.
Image labels retain upstream source and revision. These are local source builds,
not official prebuilt images; no image is published by this workflow.

Run `docker compose -f infra/docker-compose.yml build minio bucket-init` before
starting Compose, or use `infra/smoke.ps1`, which now performs that build first.
The first source build needs public GitHub/Go-module/Alpine access and may take
several minutes. BuildKit caches downloads and compilation for subsequent runs.
CI allows up to 20 minutes for the source build plus smoke within a 25-minute job.

Private bucket settings, credentials for fictional local development, loopback
ports, pgvector and anonymous-listing denial checks are unchanged. This source
build is infrastructure packaging, not a DB or object-access contract change.
