from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field

from app.modules.auth.schemas import Input

Role = Literal["ELDER", "CHILD", "CAREGIVER", "EMERGENCY_CONTACT"]
Scope = Literal["VOICE", "PORTRAIT", "FAMILY_MEMORY", "HEALTH_MEDICATION", "CONVERSATION_SUMMARY", "CAMERA_PROXIMITY", "NOTIFICATION_TO_FAMILY"]


class FamilyCreate(Input):
    name: str = Field(min_length=1, max_length=120)


class InvitationCreate(Input):
    target_role: Role
    expires_at: AwareDatetime
    max_usage: int = Field(default=1, ge=1, le=10, strict=True)
    requested_scopes: list[Scope] = Field(default_factory=list)


class InvitationAccept(Input):
    confirm_identity: Literal[True] | None = None
    requested_display_name: str | None = Field(default=None, max_length=120)


class MemberUpdate(Input):
    role: Role | None = None
    status: Literal["PENDING", "ACTIVE", "REVOKED", "LEFT"] | None = None
    permission_codes: list[str] | None = Field(default=None, max_length=50)


def timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
