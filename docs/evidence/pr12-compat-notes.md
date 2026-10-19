# Linux + Windows compatibility with main

The PR #12 Linux deployment and two Windows Tkinter client prototypes are retained. Existing main backend, Android code, migrations, API contracts, and Week 2-6 verification scripts remain authoritative.

## Known limits
- main supports DEMO login, families, invitations and /health.
- main does not yet provide /v1/devices/register, /v1/messages or delivery receipts. Windows clients query /openapi.json and present an explicit unsupported-feature message, rather than treating these as a working end-to-end messaging capability.
- Dockerized S3 uses the internal endpoint for file I/O and the public endpoint for signed PUT links.
- The Compose demo binds API and S3 to network interfaces over HTTP. Restrict them to a trusted LAN/VM network, never expose DEMO credentials to the public Internet.
- Docker build / real VM networking / native Windows GUI packaging / on-device photo PUT are not proven by source inspection or mock HTTP client tests. Verify those independently before merging.

## Commands
- Linux: `bash infra/linux/deploy.sh --host <reachable-LAN-IP>`
- Windows clients: `windows/family-client/build.ps1` and `windows/elder-demo/build.ps1` from PowerShell.
- Client mock HTTP tests: `PYTHONPATH=windows/family-client/src python -m unittest discover -s windows/family-client/tests -v`; likewise for `elder-demo`.
