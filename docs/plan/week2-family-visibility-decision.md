# Week 2 family visibility clarification

Status: ACCEPTED by the project owner on 2026-09-30: use the ACTIVE-only restriction.

## Existing conflict

- `docs/api-spec.md` §14: `GET /families/{family_id}` allows ACTIVE/PENDING membership.
- `docs/api-permission-matrix.md` §3.2: the same operation requires ACTIVE membership.
- `AGENTS.md`: a security-boundary or contract conflict stops the affected work.

## Recommended resolution

Require ACTIVE membership for the family-detail operation, following the permission
matrix. A pending invitee can see only their own pending membership through the
existing invitation-accept response and identity/membership summary; they cannot
read the family member list, content or Consent history before activation.

This preserves the current OpenAPI request and response structures and adds no
operation or DB field. If approved, clarify the corresponding API-spec sentence
and test pending-detail denial. Invitation creation is the inviter's confirmation;
the authenticated invitee's `confirm_identity=true` supplies the invitee confirmation as
defined in the existing invitation request. Family content remains denied until
the recorded membership is ACTIVE.

## Alternative

Allow PENDING members to read the existing family-detail response. This requires
explicitly relaxing the permission-matrix row and testing the narrow response;
it must not imply access to member lists, private content or Consent history.

## Independent work

Authentication/session mechanics, frozen DTO/model mapping, device kickoff records
and tests of unambiguous requirements may proceed while this decision is pending.
