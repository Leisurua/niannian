from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.modules.auth.schemas import Input
from app.modules.family.schemas import Scope


class ConsentCreate(Input):
    family_id: UUID
    subject_user_id: UUID
    grantee_user_id: UUID
    scope: Scope
    source: Literal["ONBOARDING", "SETTINGS", "IMPORT"]
    expires_at: AwareDatetime | None = None
    confirmation_text: str | None = Field(default=None, max_length=500)


class ConsentRevoke(Input):
    reason: str | None = Field(default=None, max_length=240)
