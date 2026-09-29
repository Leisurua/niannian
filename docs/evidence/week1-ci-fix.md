# Week 1 CI repair — 2026-09-29

Failing-before evidence: [run 36538066004](https://github.com/Leisurua/niannian/actions/runs/36538066004)
on `65590b0`. Backend passed. Android failed before compilation; infrastructure
failed before its services started. No test assertion has been relaxed.

| Failure | Verified cause | Repair / same-boundary verification |
| --- | --- | --- |
| Android SDK setup | The pinned setup action defaults to `tools platform-tools`; SDK manager reports `Failed to find package 'tools'` | Explicitly install `platform-tools`; retain the separate SDK 35/build-tools 35.0.0 step. Verify with the Android CI job, including full build and 12-APK scan |
| Android failure evidence | Setup failure creates no build output, so upload also failed | Always save a small job-status record; it explicitly records whether build summary exists. Keep missing-artifact checks |
| MinIO pull | Quay returns `unauthorized`; anonymous Docker Hub pull also returns 401, archived binaries return 410 | Build the same upstream source releases from fixed commits; rerun the existing pgvector/private-bucket/403 smoke without bypassing it |
| CI diagnostics | Child output was only in downloadable artifacts | Print a bounded failure-log tail as well as retaining artifacts |

The closest regression check is the actual hosted SDK setup and Compose smoke.
Local tests cannot prove that an external package or registry is available. No
mocked registry test is used as a substitute. The backend suite and wheel smoke
remain part of local verification and the unchanged CI backend job.

MinIO source provenance and build/runtime scope are documented in
`infra/minio/README.md`. The service and client versions, private bucket behavior,
database contract and all application dependencies stay unchanged. Source builds
need more time than image pulls, so infrastructure receives a bounded 20-minute
check within a 25-minute job.

Final hosted results must be read on the pushed repair commit; this document
does not turn the old failed run, local unit checks or queued runs into a PASS.
Physical-device tests remain NOT VERIFIED; the user has no test device yet.
