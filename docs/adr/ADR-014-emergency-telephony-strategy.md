# ADR-014 Emergency Telephony Strategy

- Status: Proposed
- Date: 2026-09-22
- Scope: Elder Emergency contact paths

## Context

Emergency is a product capability, but direct cellular calling depends on tablet model, SIM, cellular registration, Telecom/OEM behavior and `CALL_PHONE` permission. Android cannot always prove that a human answered.

## Decision

Use a capability matrix. Prefer a verified local Telecom/call path when SIM, provider and permission are present; otherwise use an authorized backend Push/SMS/VoIP/external path or a clearly labelled mock/demo fallback. Record `INITIATED`, `CONNECTING`, `CONNECTED`, `NO_ANSWER`, `FAILED` and `CANCELLED` only from observed results. “Intent launched” is not “human answered”.

## Consequences

No-SIM devices remain demoable through local case creation and fallback notification, but cannot claim local call success. Real-device tests must cover SIM, no SIM, denied permission, provider failure, no answer, duplicate trigger and process death before this ADR can be Accepted.
